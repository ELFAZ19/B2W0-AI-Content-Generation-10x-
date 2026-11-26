"""Stage 2: Character reference sheet and per-shot keyframes (Cloudflare FLUX / mock)."""

from __future__ import annotations

import argparse
import base64
import time
from pathlib import Path
from typing import Any

import requests

from pipeline.cache import CacheManifest, compute_input_hash, file_sha256
from pipeline.config import (
    DEFAULT_CF_FALLBACK_IMAGE_MODEL,
    PipelineConfig,
    load_config,
)
from pipeline.ffmpeg_utils import generate_mock_keyframe, generate_mock_reference_sheet
from pipeline.logger import RunLogger
from pipeline.retry import NonRetryableError, with_retry
from pipeline.schema_validator import validate_storyboard


def _call_cloudflare_image(
    config: PipelineConfig,
    *,
    prompt: str,
    seed: int,
    width: int,
    height: int,
    model: str,
) -> bytes:
    """Invoke Cloudflare Workers AI image endpoint and return PNG/JPEG bytes."""
    if not config.has_cloudflare:
        raise NonRetryableError("Cloudflare credentials missing.")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account_id}"
        f"/ai/run/{model}"
    )
    headers = {"Authorization": f"Bearer {config.cloudflare_api_token}"}
    if "flux-2" in model:
        files = {
            "prompt": (None, prompt),
            "steps": (None, "4"),
            "width": (None, str(width)),
            "height": (None, str(height)),
            "seed": (None, str(seed)),
        }
        resp = requests.post(url, headers=headers, files=files, timeout=90)
    else:
        payload = {
            "prompt": prompt,
            "steps": 4,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code in (401, 403):
        raise NonRetryableError(f"Cloudflare auth error ({resp.status_code}): {resp.text[:200]}")
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = resp.json()
        result = data.get("result") or data
        b64 = result.get("image") or result.get("b64_json")
        if not b64:
            raise RuntimeError(f"Unexpected Cloudflare JSON response keys: {list(data.keys())}")
        return base64.b64decode(b64)
    return resp.content


def _compose_keyframe_prompt(storyboard: dict[str, Any], shot: dict[str, Any]) -> str:
    style = storyboard["style_block"]
    char = storyboard["character_sheet"]
    parts = [
        style["prompt_prefix"],
        f"Palette: {style['palette']}",
        f"Lighting: {style['lighting']}",
        f"Medium: {style['medium']}",
        f"Main character consistency: {char['description']}",
        f"Shot framing ({shot['shot_size'].replace('_', ' ')}): {shot['keyframe_prompt']}",
    ]
    return ". ".join(parts)


def run_keyframes_stage(
    config: PipelineConfig,
    *,
    shot_filter: str | None = None,
    force: bool = False,
    cf_model: str | None = None,
) -> dict[str, Any]:
    """Generate reference sheet first, then per-shot keyframes conditioned on it."""
    config.ensure_dirs()
    storyboard, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    cache = CacheManifest(config.cache_manifest_path)
    logger = RunLogger(config.runs_log_path)

    model_id = cf_model or config.cloudflare_image_model
    use_live = config.resolve_provider(config.has_cloudflare, "Cloudflare Workers AI") == "live"
    provider_name = "cloudflare" if use_live else "mock"

    # 1. Character & style reference sheet
    char = storyboard["character_sheet"]
    style = storyboard["style_block"]
    ref_path = config.references_dir / f"{char['character_id']}_sheet.png"

    ref_hash = compute_input_hash(
        {
            "character_id": char["character_id"],
            "description": char["description"],
            "reference_prompts": char["reference_prompts"],
            "reference_seed": char["reference_seed"],
            "style_block": style,
            "provider": provider_name,
            "model": model_id if use_live else "mock",
        }
    )

    t_ref = time.perf_counter()
    if cache.is_valid("references", char["character_id"], ref_hash, [ref_path], force=force):
        print(f"[keyframes] ref_sheet ({char['character_id']}): CACHE HIT")
    else:
        if use_live:
            ref_prompt = (
                f"{style['prompt_prefix']}. Character model sheet (front view, 3/4 profile, expression), "
                f"{char['description']}. {char['reference_prompts'][0]}"
            )
            used_model = model_id
            try:
                img_bytes = with_retry(
                    lambda: _call_cloudflare_image(
                        config,
                        prompt=ref_prompt,
                        seed=int(char["reference_seed"]),
                        width=1024,
                        height=576,
                        model=model_id,
                    ),
                    max_attempts=3,
                )
            except Exception:
                used_model = DEFAULT_CF_FALLBACK_IMAGE_MODEL
                img_bytes = with_retry(
                    lambda: _call_cloudflare_image(
                        config,
                        prompt=ref_prompt,
                        seed=int(char["reference_seed"]),
                        width=1024,
                        height=576,
                        model=DEFAULT_CF_FALLBACK_IMAGE_MODEL,
                    ),
                    max_attempts=2,
                )
            ref_path.write_bytes(img_bytes)
        else:
            used_model = "mock"
            generate_mock_reference_sheet(
                ref_path,
                character_name=char["name"],
                description=char["description"],
                seed=int(char["reference_seed"]),
            )
        cache.record("references", char["character_id"], ref_hash, [ref_path])
        logger.log_call(
            stage="keyframes_ref",
            shot_id=None,
            provider=provider_name,
            model=used_model,
            parameters={"character_id": char["character_id"], "width": 1024, "height": 576},
            seed=int(char["reference_seed"]),
            latency_s=time.perf_counter() - t_ref,
            cache_hit=False,
            input_hash=ref_hash,
            status="ok",
            outputs=[str(ref_path)],
        )
        print(f"[keyframes] ref_sheet ({char['character_id']}): GENERATED ({used_model})")

    approved_ref_sha = file_sha256(ref_path) or ref_hash

    # 2. Per-shot keyframes conditioned on reference sheet + style_block
    generated_paths: list[Path] = []
    hits = 0
    regenerated = 0

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        if shot_filter and shot_id != shot_filter:
            continue

        out_path = config.keyframes_dir / f"{shot_id}.png"
        full_prompt = _compose_keyframe_prompt(storyboard, shot)
        shot_hash = compute_input_hash(
            {
                "shot_id": shot_id,
                "approved_ref_sha": approved_ref_sha,
                "style_block": style,
                "character_description": char["description"],
                "keyframe_prompt": shot["keyframe_prompt"],
                "shot_size": shot["shot_size"],
                "seed": int(shot["seed"]),
                "provider": provider_name,
                "model": model_id if use_live else "mock",
            }
        )

        t0 = time.perf_counter()
        if cache.is_valid("keyframes", shot_id, shot_hash, [out_path], force=force):
            hits += 1
            print(f"[keyframes] {shot_id}: CACHE HIT")
            generated_paths.append(out_path)
            continue

        if use_live:
            used_model = model_id
            try:
                img_bytes = with_retry(
                    lambda: _call_cloudflare_image(
                        config,
                        prompt=full_prompt,
                        seed=int(shot["seed"]),
                        width=1280,
                        height=720,
                        model=model_id,
                    ),
                    max_attempts=3,
                )
            except Exception:
                used_model = DEFAULT_CF_FALLBACK_IMAGE_MODEL
                img_bytes = with_retry(
                    lambda: _call_cloudflare_image(
                        config,
                        prompt=full_prompt,
                        seed=int(shot["seed"]),
                        width=1280,
                        height=720,
                        model=DEFAULT_CF_FALLBACK_IMAGE_MODEL,
                    ),
                    max_attempts=2,
                )
            out_path.write_bytes(img_bytes)
        else:
            used_model = "mock"
            generate_mock_keyframe(
                out_path,
                shot_id=shot_id,
                scene=shot["scene"],
                shot_size=shot["shot_size"],
                prompt=shot["keyframe_prompt"],
                seed=int(shot["seed"]),
            )

        cache.record("keyframes", shot_id, shot_hash, [out_path], metadata={"model": used_model})
        logger.log_call(
            stage="keyframes",
            shot_id=shot_id,
            provider=provider_name,
            model=used_model,
            parameters={"shot_size": shot["shot_size"], "width": 1280, "height": 720},
            seed=int(shot["seed"]),
            latency_s=time.perf_counter() - t0,
            cache_hit=False,
            input_hash=shot_hash,
            status="ok",
            outputs=[str(out_path)],
        )
        regenerated += 1
        generated_paths.append(out_path)
        print(f"[keyframes] {shot_id}: GENERATED ({used_model})")

    return {"paths": [str(p) for p in generated_paths], "cache_hits": hits, "regenerated": regenerated}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 2: generate reference sheet & keyframes.")
    parser.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--shot", type=str, default=None, help="Regenerate only one shot id.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(root=args.root, mode=args.mode)
    res = run_keyframes_stage(cfg, shot_filter=args.shot, force=args.force)
    print(f"[keyframes] Done: {res['regenerated']} generated, {res['cache_hits']} cached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
