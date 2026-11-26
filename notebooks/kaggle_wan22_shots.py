"""Kaggle (2x T4) batch worker for Wan 2.2 TI2V-5B image-to-video generation.

Upload `storyboard.json` and `outputs/keyframes/*.png` to a Kaggle dataset,
run this script in a Kaggle GPU (2x T4) notebook, and download the resulting
`kaggle_shots/*.mp4` files into `outputs/kaggle_shots/` locally.

Drafts at 480p first by default (`--quality draft`), saving each clip immediately
and appending per-call latency and GPU-minutes to `runs_kaggle.jsonl`.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Wan 2.2 TI2V-5B on Kaggle 2x T4.")
    parser.add_argument("--storyboard", type=Path, default=Path("storyboard.json"))
    parser.add_argument("--keyframes-dir", type=Path, default=Path("outputs/keyframes"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/kaggle_shots"))
    parser.add_argument("--log-file", type=Path, default=Path("runs_kaggle.jsonl"))
    parser.add_argument("--quality", choices=["draft", "final"], default="draft")
    parser.add_argument("--steps", type=int, default=24)
    args = parser.parse_args()

    import torch
    from diffusers import WanImageToVideoPipeline
    from diffusers.utils import export_to_video, load_image

    args.out_dir.mkdir(parents=True, exist_ok=True)
    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))

    # Draft at 480p (832x480) to conserve weekly 30h Kaggle GPU quota; finish at 720p (1280x720)
    width, height = (832, 480) if args.quality == "draft" else (1280, 720)
    model_id = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

    pipe = WanImageToVideoPipeline.from_pretrained(model_id, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        out_mp4 = args.out_dir / f"{shot_id}.mp4"
        if out_mp4.exists() and out_mp4.stat().st_size > 0:
            print(f"[kaggle-wan] {shot_id}: already generated, skipping.")
            continue

        kf_path = args.keyframes_dir / f"{shot_id}.png"
        if not kf_path.exists():
            print(f"[kaggle-wan] {shot_id}: missing keyframe {kf_path}, skipping.")
            continue

        image = load_image(str(kf_path)).resize((width, height))
        # Appendix B: For image-to-video, keep prompt focused on motion and camera only
        prompt = f"{shot['motion_prompt']} Camera: {shot['camera_movement'].replace('_', ' ')}."
        neg_prompt = storyboard["style_block"].get("negative_prompt", "")
        num_frames = min(121, max(49, int(round(min(5.0, float(shot["duration_sec"])) * 24))))
        generator = torch.Generator(device="cpu").manual_seed(int(shot["seed"]))

        t0 = time.perf_counter()
        result = pipe(
            image=image,
            prompt=prompt,
            negative_prompt=neg_prompt,
            height=height,
            width=width,
            num_frames=num_frames,
            num_inference_steps=args.steps,
            guidance_scale=5.0,
            generator=generator,
        ).frames[0]
        export_to_video(result, str(out_mp4), fps=24)
        latency_s = time.perf_counter() - t0

        record = {
            "stage": "shots",
            "shot_id": shot_id,
            "provider": "kaggle-2xt4",
            "model": "Wan-AI/Wan2.2-TI2V-5B",
            "parameters": {"width": width, "height": height, "steps": args.steps, "num_frames": num_frames},
            "seed": int(shot["seed"]),
            "latency_s": round(latency_s, 3),
            "gpu_minutes": round(latency_s / 60.0, 4),
            "status": "ok",
        }
        with args.log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"[kaggle-wan] {shot_id}: saved {out_mp4} in {latency_s:.1f}s")


if __name__ == "__main__":
    main()
