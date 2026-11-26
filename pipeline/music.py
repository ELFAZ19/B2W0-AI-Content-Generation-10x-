"""Stage 5: Score candidate generation via ACE-Step 1.5 worker or FFmpeg underscore fallback."""

from __future__ import annotations

import argparse
import base64
import shutil
import time
from pathlib import Path
from typing import Any

import requests

from pipeline.cache import CacheManifest, compute_input_hash, file_sha256
from pipeline.config import DEFAULT_MUSIC_MODEL, PipelineConfig, load_config
from pipeline.ffmpeg_utils import generate_silent_or_tone_wav, normalize_stem
from pipeline.logger import RunLogger
from pipeline.retry import NonRetryableError, with_retry
from pipeline.schema_validator import validate_storyboard


def _call_acestep_worker(
    *,
    worker_url: str,
    worker_token: str | None,
    caption: str,
    lyrics: str,
    tempo_bpm: int,
    key: str,
    duration_sec: float,
    seed: int,
    out_wav: Path,
) -> tuple[float, float]:
    """Call an external ACE-Step 1.5 worker returning WAV/MP3 audio."""
    headers = {}
    if worker_token:
        headers["Authorization"] = f"Bearer {worker_token}"
    payload = {
        "caption": caption,
        "lyrics": lyrics,
        "bpm": tempo_bpm,
        "keyscale": key,
        "duration": duration_sec,
        "seed": seed,
    }
    t0 = time.perf_counter()

    def _post() -> bytes:
        resp = requests.post(f"{worker_url.rstrip('/')}/generate", json=payload, headers=headers, timeout=300)
        if resp.status_code in (401, 403):
            raise NonRetryableError(f"ACE-Step worker auth failed ({resp.status_code})")
        if resp.status_code >= 400:
            raise RuntimeError(f"ACE-Step worker error ({resp.status_code}): {resp.text[:300]}")
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return base64.b64decode(resp.json()["audio_b64"])
        return resp.content

    audio_bytes = with_retry(_post, max_attempts=2)
    latency_s = time.perf_counter() - t0
    raw_path = out_wav.with_suffix(".raw.audio")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(audio_bytes)
    normalize_stem(raw_path, out_wav, target_i=-22.0)
    raw_path.unlink(missing_ok=True)
    return latency_s, latency_s / 60.0


def run_music_stage(
    config: PipelineConfig,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Generate score candidates (e.g. 3 seeds), cache per seed, and select chosen track."""
    config.ensure_dirs()
    storyboard, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    music_cfg = storyboard["music"]
    cache = CacheManifest(config.cache_manifest_path)
    logger = RunLogger(config.runs_log_path)

    use_live = (
        music_cfg["provider"] == "ace-step"
        and config.mode != "mock"
        and config.has_acestep_worker
    )
    if config.mode == "live" and not config.has_acestep_worker:
        raise RuntimeError("PIPELINE_MODE=live requires ACESTEP_WORKER_URL for music stage.")

    base_seed = int(music_cfg.get("base_seed", 4200))
    num_candidates = int(music_cfg["candidates"])
    candidate_seeds = [base_seed + i for i in range(num_candidates)]

    candidate_paths: list[Path] = []
    hits = 0
    regenerated = 0

    for idx, seed in enumerate(candidate_seeds):
        cand_key = f"candidate_{idx}"
        out_wav = config.music_dir / f"candidate_{idx}_seed_{seed}.wav"
        kaggle_cand = config.outputs_dir / "kaggle_music" / f"candidate_{idx}.wav"

        if kaggle_cand.exists():
            provider_tag = "kaggle-import"
            model_tag = DEFAULT_MUSIC_MODEL
        elif use_live:
            provider_tag = "acestep-worker"
            model_tag = DEFAULT_MUSIC_MODEL
        else:
            provider_tag = "ffmpeg-fallback"
            model_tag = "ffmpeg-synth-audio"

        input_hash = compute_input_hash(
            {
                "candidate_index": idx,
                "seed": seed,
                "kaggle_sha256": file_sha256(kaggle_cand) if kaggle_cand.exists() else None,
                "caption": music_cfg["caption"],
                "lyrics": music_cfg.get("lyrics", "[instrumental]"),
                "tempo_bpm": int(music_cfg["tempo_bpm"]),
                "key": music_cfg["key"],
                "duration_sec": float(music_cfg["duration_sec"]),
                "model": model_tag,
                "provider": provider_tag,
            }
        )

        if cache.is_valid("music", cand_key, input_hash, [out_wav], force=force):
            hits += 1
            print(f"[music] {cand_key} (seed={seed}): CACHE HIT")
            candidate_paths.append(out_wav)
            continue

        if kaggle_cand.exists():
            t0 = time.perf_counter()
            normalize_stem(kaggle_cand, out_wav, target_i=-22.0)
            latency_s = time.perf_counter() - t0
            gpu_min = 0.0
        elif use_live:
            assert config.acestep_worker_url is not None
            latency_s, gpu_min = _call_acestep_worker(
                worker_url=config.acestep_worker_url,
                worker_token=config.acestep_worker_token,
                caption=music_cfg["caption"],
                lyrics=music_cfg.get("lyrics", "[instrumental]"),
                tempo_bpm=int(music_cfg["tempo_bpm"]),
                key=music_cfg["key"],
                duration_sec=float(music_cfg["duration_sec"]),
                seed=seed,
                out_wav=out_wav,
            )
        else:
            t0 = time.perf_counter()
            base_hz = 146.83 + idx * 14.0
            raw_wav = out_wav.with_suffix(".raw.wav")
            generate_silent_or_tone_wav(
                raw_wav,
                float(music_cfg["duration_sec"]),
                freq_hz=base_hz,
                amplitude=0.08,
            )
            normalize_stem(raw_wav, out_wav, target_i=-22.0)
            raw_wav.unlink(missing_ok=True)
            latency_s = time.perf_counter() - t0
            gpu_min = 0.0

        cache.record("music", cand_key, input_hash, [out_wav], metadata={"seed": seed, "model": model_tag})
        logger.log_call(
            stage="music",
            shot_id=cand_key,
            provider=provider_tag,
            model=model_tag,
            parameters={
                "tempo_bpm": int(music_cfg["tempo_bpm"]),
                "key": music_cfg["key"],
                "duration_sec": float(music_cfg["duration_sec"]),
                "instrumental": bool(music_cfg["instrumental"]),
            },
            seed=seed,
            latency_s=latency_s,
            gpu_minutes=gpu_min,
            cache_hit=False,
            input_hash=input_hash,
            status="ok",
            outputs=[str(out_wav)],
        )
        regenerated += 1
        candidate_paths.append(out_wav)
        print(f"[music] {cand_key} (seed={seed}): GENERATED ({model_tag})")

    selected_idx = int(music_cfg["chosen_candidate_index"])
    selected_src = candidate_paths[selected_idx]
    selected_dst = config.music_dir / "score_selected.wav"
    shutil.copy2(selected_src, selected_dst)

    return {
        "cache_hits": hits,
        "regenerated": regenerated,
        "selected_score": str(selected_dst),
        "selected_candidate_index": selected_idx,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate music score candidates and select chosen track.")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(root=args.root, mode=args.mode)
    res = run_music_stage(cfg, force=args.force)
    print(f"[music] Done: {res['regenerated']} generated, {res['cache_hits']} cached -> {res['selected_score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
