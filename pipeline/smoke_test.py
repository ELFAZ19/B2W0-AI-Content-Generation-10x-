"""Phase 1 Step 1 smoke test: verify tools, schema, and configured provider APIs."""

from __future__ import annotations

import argparse
import base64
import shutil
import subprocess
import time
from pathlib import Path

import requests

from pipeline.config import (
    DEFAULT_CF_FALLBACK_IMAGE_MODEL,
    DEFAULT_GEMINI_TEXT_MODEL,
    DEFAULT_GEMINI_TTS_MODEL,
    PipelineConfig,
    load_config,
)
from pipeline.logger import RunLogger
from pipeline.schema_validator import validate_storyboard


def run_smoke_test(config: PipelineConfig) -> dict[str, str]:
    """Validate local tools and optionally ping live APIs, logging latency to runs.jsonl."""
    logger = RunLogger(config.runs_log_path)
    results: dict[str, str] = {}

    # 1. Storyboard schema validation
    t0 = time.perf_counter()
    _, warnings = validate_storyboard(config.storyboard_path, config.schema_path)
    results["schema"] = f"ok ({len(warnings)} warnings)"
    logger.log_call(
        stage="smoke_test",
        shot_id=None,
        provider="local",
        model="jsonschema",
        parameters={"storyboard": str(config.storyboard_path.name)},
        seed=None,
        latency_s=time.perf_counter() - t0,
        status="ok",
    )

    # 2. FFmpeg availability
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        results["ffmpeg"] = "missing"
        raise RuntimeError("ffmpeg and ffprobe must be installed and on PATH.")
    ver = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    results["ffmpeg"] = ver

    if config.mode == "mock":
        results["gemini_text"] = "skipped (mock mode)"
        results["gemini_tts"] = "skipped (mock mode)"
        results["cloudflare_flux"] = "skipped (mock mode)"
        return results

    # 3. Gemini text + TTS ping
    if config.has_gemini:
        from google import genai

        client = genai.Client(api_key=config.gemini_api_key, http_options={"api_version": "v1beta"})
        t1 = time.perf_counter()
        try:
            resp = client.interactions.create(
                model=DEFAULT_GEMINI_TEXT_MODEL,
                input="Reply with the single word: READY",
            )
            dt = time.perf_counter() - t1
            text = (resp.output_text or "").strip()
            results["gemini_text"] = f"ok ({dt:.2f}s): {text[:40]}"
            logger.log_call(
                stage="smoke_test",
                shot_id=None,
                provider="gemini",
                model=DEFAULT_GEMINI_TEXT_MODEL,
                parameters={"smoke": True},
                seed=None,
                latency_s=dt,
                status="ok",
            )
        except Exception as exc:
            dt = time.perf_counter() - t1
            results["gemini_text"] = f"error: {exc}"
            logger.log_call(
                stage="smoke_test",
                shot_id=None,
                provider="gemini",
                model=DEFAULT_GEMINI_TEXT_MODEL,
                parameters={"smoke": True},
                seed=None,
                latency_s=dt,
                status="error",
                error=str(exc),
            )

        t2 = time.perf_counter()
        try:
            tts = client.interactions.create(
                model=DEFAULT_GEMINI_TTS_MODEL,
                input=[
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": "Selam.",
                                "annotations": [{"type": "speech_metadata", "style": "calm and warm"}],
                            }
                        ],
                    }
                ],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": "Charon"}]},
            )
            dt = time.perf_counter() - t2
            out_dir = config.outputs_dir / "smoke"
            out_dir.mkdir(parents=True, exist_ok=True)
            audio_bytes = base64.b64decode(tts.output_audio.data)
            (out_dir / "smoke_tts.wav").write_bytes(audio_bytes)
            results["gemini_tts"] = f"ok ({dt:.2f}s, {len(audio_bytes)} bytes)"
            logger.log_call(
                stage="smoke_test",
                shot_id=None,
                provider="gemini",
                model=DEFAULT_GEMINI_TTS_MODEL,
                parameters={"voice": "Charon", "smoke": True},
                seed=None,
                latency_s=dt,
                status="ok",
                outputs=[str(out_dir / "smoke_tts.wav")],
            )
        except Exception as exc:
            dt = time.perf_counter() - t2
            results["gemini_tts"] = f"error: {exc}"
            logger.log_call(
                stage="smoke_test",
                shot_id=None,
                provider="gemini",
                model=DEFAULT_GEMINI_TTS_MODEL,
                parameters={"voice": "Charon", "smoke": True},
                seed=None,
                latency_s=dt,
                status="error",
                error=str(exc),
            )
    else:
        results["gemini_text"] = "unconfigured (GEMINI_API_KEY not set)"
        results["gemini_tts"] = "unconfigured (GEMINI_API_KEY not set)"

    # 4. Cloudflare Workers AI ping
    if config.has_cloudflare:
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account_id}"
            f"/ai/run/{DEFAULT_CF_FALLBACK_IMAGE_MODEL}"
        )
        t3 = time.perf_counter()
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {config.cloudflare_api_token}"},
                json={"prompt": "Warm brass vintage radio on wooden table, minimal test", "steps": 4},
                timeout=45,
            )
            r.raise_for_status()
            dt = time.perf_counter() - t3
            results["cloudflare_flux"] = f"ok ({dt:.2f}s, status={r.status_code})"
            logger.log_call(
                stage="smoke_test",
                shot_id=None,
                provider="cloudflare",
                model=DEFAULT_CF_FALLBACK_IMAGE_MODEL,
                parameters={"num_steps": 4, "smoke": True},
                seed=None,
                latency_s=dt,
                status="ok",
            )
        except Exception as exc:
            dt = time.perf_counter() - t3
            results["cloudflare_flux"] = f"error: {exc}"
            logger.log_call(
                stage="smoke_test",
                shot_id=None,
                provider="cloudflare",
                model=DEFAULT_CF_FALLBACK_IMAGE_MODEL,
                parameters={"num_steps": 4, "smoke": True},
                seed=None,
                latency_s=dt,
                status="error",
                error=str(exc),
            )
    else:
        results["cloudflare_flux"] = "unconfigured (CLOUDFLARE_* not set)"

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test tools and provider credentials.")
    parser.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)

    cfg = load_config(root=args.root, mode=args.mode)
    results = run_smoke_test(cfg)
    for k, v in results.items():
        print(f"[smoke] {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
