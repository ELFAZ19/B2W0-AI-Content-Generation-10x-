"""Kaggle/Colab worker script for ACE-Step 1.5 score candidate generation (<4 GB VRAM).

Usage inside Kaggle/Colab:
1. Install ACE-Step 1.5 (https://github.com/ACE-Step/ACE-Step-1.5).
2. Upload `storyboard.json` to `/kaggle/working/project/storyboard.json`.
3. Run:
   python kaggle_acestep_worker.py --project-dir /kaggle/working/project
4. Copy `outputs/kaggle_music/candidate_*.wav` into your local `outputs/kaggle_music/`
   so `python -m pipeline music` normalizes and caches them automatically!
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch ACE-Step 1.5 candidate generator.")
    parser.add_argument("--project-dir", type=Path, required=True)
    args = parser.parse_args()

    sb_path = args.project_dir / "storyboard.json"
    storyboard = json.loads(sb_path.read_text(encoding="utf-8"))
    music_cfg = storyboard["music"]

    out_dir = args.project_dir / "outputs" / "kaggle_music"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_log = args.project_dir / "runs_kaggle.jsonl"

    base_seed = int(music_cfg.get("base_seed", 4200))
    num_candidates = int(music_cfg["candidates"])

    # Import ACE-Step 1.5 pipeline (installed from github.com/ACE-Step/ACE-Step-1.5)
    from acestep.pipeline_ace_step import ACEStepPipeline

    pipe = ACEStepPipeline()
    pipe.load_checkpoint()

    for idx in range(num_candidates):
        seed = base_seed + idx
        out_wav = out_dir / f"candidate_{idx}.wav"
        if out_wav.exists() and out_wav.stat().st_size > 0:
            print(f"[kaggle-acestep] candidate_{idx}: already exists, skipping.")
            continue

        t0 = time.perf_counter()
        lyrics = "[instrumental]" if music_cfg["instrumental"] else music_cfg.get("lyrics", "")
        pipe(
            audio_duration=float(music_cfg["duration_sec"]),
            prompt=music_cfg["caption"],
            lyrics=lyrics,
            infer_step=27,
            guidance_scale=7.0,
            manual_seeds=[seed],
            save_path=str(out_wav),
        )
        latency_s = time.perf_counter() - t0
        gpu_min = latency_s / 60.0

        log_entry = {
            "stage": "music",
            "shot_id": f"candidate_{idx}",
            "provider": "kaggle-gpu",
            "model": "ACE-Step/ACE-Step-1.5",
            "parameters": {
                "tempo_bpm": music_cfg["tempo_bpm"],
                "key": music_cfg["key"],
                "duration_sec": music_cfg["duration_sec"],
                "instrumental": music_cfg["instrumental"],
            },
            "seed": seed,
            "latency_s": round(latency_s, 3),
            "gpu_minutes": round(gpu_min, 4),
            "status": "ok",
            "outputs": [str(out_wav)],
        }
        with runs_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_entry) + "\n")
        print(f"[kaggle-acestep] candidate_{idx} (seed={seed}): saved ({latency_s:.1f}s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
