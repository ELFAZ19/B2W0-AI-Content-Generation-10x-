"""Kaggle 2x T4 / Colab worker script for Wan 2.2 TI2V-5B image-to-video batching.

Usage inside Kaggle Notebook:
1. Upload `storyboard.json` and `outputs/keyframes/` to `/kaggle/working/project/`.
2. Install Wan 2.2 / diffusers dependencies on GPU runtime (T4 x2).
3. Run:
   python kaggle_wan22_worker.py --project-dir /kaggle/working/project --quality draft
4. Download `outputs/kaggle_shots/` back into your local repo's `outputs/kaggle_shots/`
   so `python -m pipeline shots` automatically picks them up, trims weak frames,
   conforms to 24fps, and caches them!
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch Wan 2.2 TI2V-5B generation for Kaggle/Colab.")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--quality", choices=["draft", "final"], default="draft")
    parser.add_argument("--model-id", default="Wan-AI/Wan2.2-TI2V-5B-Diffusers")
    parser.add_argument("--steps", type=int, default=30)
    args = parser.parse_args()

    sb_path = args.project_dir / "storyboard.json"
    storyboard = json.loads(sb_path.read_text(encoding="utf-8"))
    kf_dir = args.project_dir / "outputs" / "keyframes"
    out_dir = args.project_dir / "outputs" / "kaggle_shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_log = args.project_dir / "runs_kaggle.jsonl"

    # Draft at 480p (832x480) to conserve weekly 30h Kaggle GPU quota; finish at 720p (1280x720)
    width, height = (832, 480) if args.quality == "draft" else (1280, 720)

    import torch
    from diffusers import WanImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    pipe = WanImageToVideoPipeline.from_pretrained(args.model_id, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        out_mp4 = out_dir / f"{shot_id}.mp4"
        if out_mp4.exists() and out_mp4.stat().st_size > 0:
            print(f"[kaggle-wan22] {shot_id}: already saved, skipping.")
            continue

        kf_path = kf_dir / f"{shot_id}.png"
        if not kf_path.exists():
            print(f"[kaggle-wan22] {shot_id}: missing keyframe {kf_path}, skipping.")
            continue

        image = load_image(str(kf_path)).resize((width, height))
        # Image-to-video prompt uses ONLY motion and camera (subject is already fixed in keyframe)
        prompt = f"{shot['motion_prompt']}, {shot['camera_movement'].replace('_', ' ')}"
        num_frames = min(121, max(49, int(round(min(5.0, float(shot["duration_sec"])) * 24)) + 1))

        t0 = time.perf_counter()
        generator = torch.Generator(device="cpu").manual_seed(int(shot["seed"]))
        output = pipe(
            image=image,
            prompt=prompt,
            negative_prompt=storyboard["style_block"]["negative_prompt"],
            width=width,
            height=height,
            num_frames=num_frames,
            num_inference_steps=args.steps,
            guidance_scale=5.0,
            generator=generator,
        ).frames[0]
        export_to_video(output, str(out_mp4), fps=24)
        latency_s = time.perf_counter() - t0
        gpu_min = latency_s / 60.0

        log_entry = {
            "stage": "shots",
            "shot_id": shot_id,
            "provider": "kaggle-2xT4",
            "model": "Wan-AI/Wan2.2-TI2V-5B",
            "parameters": {"quality": args.quality, "width": width, "height": height, "steps": args.steps},
            "seed": int(shot["seed"]),
            "latency_s": round(latency_s, 3),
            "gpu_minutes": round(gpu_min, 4),
            "status": "ok",
            "outputs": [str(out_mp4)],
        }
        with runs_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_entry) + "\n")
        print(f"[kaggle-wan22] {shot_id}: saved ({latency_s:.1f}s / {gpu_min:.2f} GPU min)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
