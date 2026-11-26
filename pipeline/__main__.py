"""Unified CLI entry point for running individual stages or the full film pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipeline import assemble, keyframes, music, narration, script, shots, smoke_test
from pipeline.config import PipelineConfig, load_config
from pipeline.schema_validator import validate_storyboard


def run_full_pipeline(
    config: PipelineConfig,
    *,
    quality: str = "final",
    force: bool = False,
) -> dict[str, object]:
    """Validate storyboard.json and run script -> narration -> keyframes -> shots -> music -> assemble."""
    config.ensure_dirs()
    validate_storyboard(config.storyboard_path, config.schema_path)
    scr_res = script.run_script_stage(config, force=force)
    nar_res = narration.run_narration_stage(config, force=force)
    kf_res = keyframes.run_keyframes_stage(config, force=force)
    shot_res = shots.run_shots_stage(config, quality=quality, force=force)
    mus_res = music.run_music_stage(config, force=force)
    asm_res = assemble.run_assemble_stage(config, cut_type="final", quality=quality, force=force)
    return {
        "script": str(scr_res),
        "narration": nar_res,
        "keyframes": kf_res,
        "shots": shot_res,
        "music": mus_res,
        "assemble": asm_res,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Heritage Short AI video generation pipeline CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the full end-to-end film pipeline.")
    p_run.add_argument("--root", type=Path, default=None)
    p_run.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    p_run.add_argument("--quality", choices=["draft", "final"], default="final")
    p_run.add_argument("--force", action="store_true")

    p_val = sub.add_parser("validate", help="Validate storyboard.json against schema and consent gate.")
    p_val.add_argument("--root", type=Path, default=None)

    p_smoke = sub.add_parser("smoke", help="Smoke-test configured external APIs and log latency.")
    p_smoke.add_argument("--root", type=Path, default=None)
    p_smoke.add_argument("--mode", choices=["auto", "live", "mock"], default=None)

    for name in ("script", "narration", "keyframes", "shots", "music", "assemble"):
        sp = sub.add_parser(name, help=f"Run only the {name} stage.")
        sp.add_argument("extra", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    if args.command == "run":
        cfg = load_config(root=args.root, mode=args.mode)
        res = run_full_pipeline(cfg, quality=args.quality, force=args.force)
        print(f"[pipeline] Complete! Outputs: {res['assemble']['outputs']}")
        return 0
    if args.command == "validate":
        cfg = load_config(root=args.root)
        sb, warnings = validate_storyboard(cfg.storyboard_path, cfg.schema_path)
        dur = sum(float(s["duration_sec"]) for s in sb["shots"])
        print(f"[validate] OK: {sb['project']['title']!r} ({len(sb['shots'])} shots, {dur:.1f}s, {len(warnings)} warnings)")
        return 0
    if args.command == "smoke":
        smoke_args: list[str] = []
        if args.root:
            smoke_args.extend(["--root", str(args.root)])
        if args.mode:
            smoke_args.extend(["--mode", args.mode])
        return smoke_test.main(smoke_args)

    stage_map = {
        "script": script.main,
        "narration": narration.main,
        "keyframes": keyframes.main,
        "shots": shots.main,
        "music": music.main,
        "assemble": assemble.main,
    }
    return stage_map[args.command](args.extra)


if __name__ == "__main__":
    raise SystemExit(main())
