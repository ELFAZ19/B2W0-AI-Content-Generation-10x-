"""Kaggle / Colab worker for ACE-Step 1.5 score candidate generation (<4 GB VRAM).

Generates N candidate tracks (default 3) from `storyboard.json`'s `music` block
into `outputs/kaggle_music/candidate_0.wav` .. `candidate_{N-1}.wav`.
Copy them into local `outputs/kaggle_music/` and run `python -m pipeline music`.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ACE-Step 1.5 score candidates on Kaggle/Colab.")
    parser.add_argument("--storyboard", type=Path, default=Path("storyboard.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/kaggle_music"))
    parser.add_argument("--log-file", type=Path, default=Path("runs_acestep.jsonl"))
    args = parser.parse_args()

    from acestep.pipeline_ace_step import ACEStepPipeline

    args.out_dir.mkdir(parents=True, exist_ok=True)
    sb = json.loads(args.storyboard.read_text(encoding="utf-8"))
    music_cfg = sb["music"]

    pipe = ACEStepPipeline(dtype="bfloat16", cpu_offload=True)
    base_seed = int(music_cfg.get("base_seed", 4200))

    for idx in range(int(music_cfg["candidates"])):
        seed = base_seed + idx
        out_wav = args.out_dir / f"candidate_{idx}.wav"
        t0 = time.perf_counter()
        pipe(
            audio_duration=float(music_cfg["duration_sec"]),
            prompt=f"{music_cfg['caption']}, {music_cfg['tempo_bpm']} bpm, {music_cfg['key']}",
            lyrics="[instrumental]" if music_cfg.get("instrumental", True) else music_cfg.get("lyrics", ""),
            manual_seeds=[seed],
            save_path=str(out_wav),
        )
        latency_s = time.perf_counter() - t0
        record = {
            "stage": "music",
            "shot_id": None,
            "provider": "kaggle-acestep",
            "model": "ACE-Step/ACE-Step-1.5",
            "parameters": {
                "candidate_index": idx,
                "tempo_bpm": music_cfg["tempo_bpm"],
                "key": music_cfg["key"],
                "duration_sec": music_cfg["duration_sec"],
            },
            "seed": seed,
            "latency_s": round(latency_s, 3),
            "gpu_minutes": round(latency_s / 60.0, 4),
            "status": "ok",
        }
        with args.log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"[kaggle-acestep] candidate_{idx} (seed={seed}) saved in {latency_s:.1f}s")


if __name__ == "__main__":
    main()
