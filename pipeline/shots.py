"""Stage 4: Moving shots via Wan 2.2 TI2V-5B worker or FFmpeg Ken Burns fallback."""

from __future__ import annotations

import argparse
import base64
import time
from pathlib import Path
from typing import Any

import requests

from pipeline.cache import CacheManifest, compute_input_hash, file_sha256
from pipeline.config import DEFAULT_VIDEO_MODEL, PipelineConfig, load_config
from pipeline.ffmpeg_utils import render_still_or_ken_burns_clip, run_cmd
from pipeline.logger import RunLogger
from pipeline.retry import NonRetryableError, with_retry
from pipeline.schema_validator import validate_storyboard


_CAMERA_TO_FALLBACK = {
    "static": "static",
    "slow_push_in": "zoom_in",
    "dolly_in": "zoom_in",
    "slow_pull_out": "zoom_out",
    "pan_left": "pan_left",
    "pan_right": "pan_right",
    "tilt_up": "zoom_in",
    "tilt_down": "zoom_out",
    "ken_burns": "zoom_in",
}


def _call_wan_worker(
    *,
    worker_url: str,
    worker_token: str | None,
    keyframe_path: Path,
    motion_prompt: str,
    camera: str,
    duration_sec: float,
    seed: int,
    width: int,
    height: int,
    out_mp4: Path,
) -> tuple[float, float]:
    """Call an external Wan 2.2 TI2V-5B worker (Kaggle/Colab/HF Space) returning MP4 bytes."""
    headers = {}
    if worker_token:
        headers["Authorization"] = f"Bearer {worker_token}"

    payload = {
        "image_b64": base64.b64encode(keyframe_path.read_bytes()).decode("ascii"),
        "prompt": f"{motion_prompt}, camera {camera.replace('_', ' ')}",
        "duration_sec": min(5.0, duration_sec),
        "width": width,
        "height": height,
        "fps": 24,
        "seed": seed,
    }
    t0 = time.perf_counter()

    def _post() -> bytes:
        resp = requests.post(f"{worker_url.rstrip('/')}/generate", json=payload, headers=headers, timeout=600)
        if resp.status_code in (401, 403):
            raise NonRetryableError(f"Wan worker auth failed ({resp.status_code})")
        if resp.status_code >= 400:
            raise RuntimeError(f"Wan worker error ({resp.status_code}): {resp.text[:300]}")
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return base64.b64decode(resp.json()["video_b64"])
        return resp.content

    mp4_bytes = with_retry(_post, max_attempts=2)
    latency_s = time.perf_counter() - t0
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_mp4.write_bytes(mp4_bytes)
    return latency_s, latency_s / 60.0


def _fit_clip_to_duration(
    src_mp4: Path,
    dst_mp4: Path,
    *,
    duration_sec: float,
    trim_start_sec: float = 0.0,
    fps: int = 24,
) -> None:
    """Trim weak leading frames and pad/loop cleanly to exact shot duration."""
    dst_mp4.parent.mkdir(parents=True, exist_ok=True)
    vf_parts = [f"fps={fps}", "format=yuv420p"]
    if trim_start_sec > 0:
        vf_parts.insert(0, f"trim=start={trim_start_sec:.3f},setpts=PTS-STARTPTS")
    run_cmd([
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(src_mp4),
        "-t",
        f"{duration_sec:.3f}",
        "-vf",
        ",".join(vf_parts),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-an",
        str(dst_mp4),
    ])


def run_shots_stage(
    config: PipelineConfig,
    *,
    quality: str = "final",
    shot_filter: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate moving video clips for each shot (Wan 2.2 worker, Kaggle drop-in, or Ken Burns fallback)."""
    config.ensure_dirs()
    storyboard, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    cache = CacheManifest(config.cache_manifest_path)
    logger = RunLogger(config.runs_log_path)

    use_wan = config.mode == "live" or (config.mode == "auto" and config.has_wan_worker)
    if config.mode == "live" and not config.has_wan_worker:
        raise RuntimeError("PIPELINE_MODE=live requires WAN_WORKER_URL for shots stage.")

    width, height = (832, 480) if quality == "draft" else (1280, 720)
    hits = 0
    regenerated = 0

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        if shot_filter and shot_id != shot_filter:
            continue

        keyframe_path = config.keyframes_dir / f"{shot_id}.png"
        if not keyframe_path.exists():
            raise FileNotFoundError(
                f"Keyframe missing for {shot_id}: {keyframe_path}. Run keyframes stage first."
            )

        out_mp4 = config.shots_dir / f"{shot_id}.mp4"
        kaggle_clip = config.outputs_dir / "kaggle_shots" / f"{shot_id}.mp4"
        duration_sec = float(shot["duration_sec"])
        camera = shot["camera_movement"]
        fallback_motion = shot.get("fallback_motion") or _CAMERA_TO_FALLBACK.get(camera, "zoom_in")

        if kaggle_clip.exists():
            provider_tag = "kaggle-import"
            model_tag = DEFAULT_VIDEO_MODEL
        elif use_wan and shot.get("video_backend", "auto") != "ken_burns":
            provider_tag = "wan-worker"
            model_tag = DEFAULT_VIDEO_MODEL
        else:
            provider_tag = "ffmpeg-fallback"
            model_tag = "ffmpeg-ken-burns"

        input_hash = compute_input_hash(
            {
                "shot_id": shot_id,
                "keyframe_sha256": file_sha256(keyframe_path),
                "kaggle_sha256": file_sha256(kaggle_clip) if kaggle_clip.exists() else None,
                "motion_prompt": shot["motion_prompt"],
                "camera_movement": camera,
                "fallback_motion": fallback_motion,
                "duration_sec": duration_sec,
                "trim_start_sec": float(shot.get("trim_start_sec", 0.0)),
                "trim_end_sec": float(shot.get("trim_end_sec", 0.0)),
                "seed": int(shot["seed"]),
                "quality": quality,
                "model": model_tag,
            }
        )

        if cache.is_valid("shots", shot_id, input_hash, [out_mp4], force=force):
            hits += 1
            print(f"[shots] {shot_id}: CACHE HIT")
            continue

        if kaggle_clip.exists():
            t0 = time.perf_counter()
            _fit_clip_to_duration(
                kaggle_clip,
                out_mp4,
                duration_sec=duration_sec,
                trim_start_sec=float(shot.get("trim_start_sec", 0.0)),
            )
            latency_s = time.perf_counter() - t0
            gpu_min = 0.0
        elif provider_tag == "wan-worker":
            assert config.wan_worker_url is not None
            raw_mp4 = config.shots_dir / f"{shot_id}_raw.mp4"
            try:
                latency_s, gpu_min = _call_wan_worker(
                    worker_url=config.wan_worker_url,
                    worker_token=config.wan_worker_token,
                    keyframe_path=keyframe_path,
                    motion_prompt=shot["motion_prompt"],
                    camera=camera,
                    duration_sec=duration_sec,
                    seed=int(shot["seed"]),
                    width=width,
                    height=height,
                    out_mp4=raw_mp4,
                )
                _fit_clip_to_duration(
                    raw_mp4,
                    out_mp4,
                    duration_sec=duration_sec,
                    trim_start_sec=float(shot.get("trim_start_sec", 0.0)),
                )
                raw_mp4.unlink(missing_ok=True)
            except Exception as exc:
                if config.mode == "live":
                    raise
                print(f"[shots] {shot_id}: Wan worker failed ({exc}); falling back to Ken Burns.")
                logger.log_call(
                    stage="shots",
                    shot_id=shot_id,
                    provider="wan-worker",
                    model=DEFAULT_VIDEO_MODEL,
                    parameters={"quality": quality, "width": width, "height": height},
                    seed=int(shot["seed"]),
                    latency_s=0.0,
                    status="failed_fallback",
                    error=str(exc),
                )
                t0 = time.perf_counter()
                render_still_or_ken_burns_clip(
                    keyframe_path,
                    out_mp4,
                    duration_sec,
                    width,
                    height,
                    motion=fallback_motion,
                )
                latency_s = time.perf_counter() - t0
                gpu_min = 0.0
                model_tag = "ffmpeg-ken-burns"
                provider_tag = "ffmpeg-fallback"
        else:
            t0 = time.perf_counter()
            render_still_or_ken_burns_clip(
                keyframe_path,
                out_mp4,
                duration_sec,
                width,
                height,
                motion=fallback_motion,
            )
            latency_s = time.perf_counter() - t0
            gpu_min = 0.0

        cache.record("shots", shot_id, input_hash, [out_mp4], metadata={"model": model_tag, "quality": quality})
        logger.log_call(
            stage="shots",
            shot_id=shot_id,
            provider=provider_tag,
            model=model_tag,
            parameters={"quality": quality, "width": width, "height": height, "duration_sec": duration_sec},
            seed=int(shot["seed"]),
            latency_s=latency_s,
            gpu_minutes=gpu_min,
            cache_hit=False,
            input_hash=input_hash,
            status="ok",
            outputs=[str(out_mp4)],
        )
        regenerated += 1
        print(f"[shots] {shot_id}: GENERATED ({model_tag}, {width}x{height})")

    return {"cache_hits": hits, "regenerated": regenerated, "quality": quality}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate moving video shots from keyframes.")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--quality", choices=["draft", "final"], default="final")
    parser.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    parser.add_argument("--shot", type=str, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(root=args.root, mode=args.mode)
    res = run_shots_stage(cfg, quality=args.quality, shot_filter=args.shot, force=args.force)
    print(f"[shots] Done: {res['regenerated']} generated, {res['cache_hits']} cached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
