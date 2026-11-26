"""Stage 6: Deterministic FFmpeg assembly (radio cut, rough cut, and 9:16 + 16:9 final exports)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from pipeline.cache import CacheManifest, compute_input_hash, file_sha256
from pipeline.config import PipelineConfig, load_config
from pipeline.ffmpeg_utils import (
    generate_silent_or_tone_wav,
    mix_with_sidechain_ducking,
    render_end_card_image,
    render_still_or_ken_burns_clip,
    run_cmd,
    two_pass_loudnorm,
)
from pipeline.schema_validator import validate_storyboard


ASPECT_TARGETS: dict[str, tuple[int, int, int, int]] = {
    # label: (final_w, final_h, draft_w, draft_h)
    "9x16": (1080, 1920, 540, 960),
    "16x9": (1920, 1080, 854, 480),
}


def _build_master_audio(
    narration_wav: Path,
    music_wav: Path,
    total_duration_sec: float,
    work_dir: Path,
) -> Path:
    ducked_wav = work_dir / "mix_ducked.wav"
    norm_wav = work_dir / "mix_loudnorm_14lufs.wav"
    mix_with_sidechain_ducking(narration_wav, music_wav, ducked_wav, total_duration_sec)
    two_pass_loudnorm(ducked_wav, norm_wav, target_i=-14.0, target_tp=-1.0)
    return norm_wav


def _render_end_card_clip(
    storyboard: dict[str, Any],
    width: int,
    height: int,
    work_dir: Path,
    fps: int = 24,
) -> Path:
    ec = storyboard["end_card"]
    duration_sec = float(ec["duration_sec"])
    img_path = work_dir / f"end_card_{width}x{height}.png"
    clip_path = work_dir / f"end_card_{width}x{height}.mp4"
    render_end_card_image(
        ec["title"],
        ec["disclosure_text"],
        ec.get("credits", ""),
        width,
        height,
        img_path,
    )
    render_still_or_ken_burns_clip(
        img_path,
        clip_path,
        duration_sec=duration_sec,
        width=width,
        height=height,
        motion="static",
        fps=fps,
    )
    return clip_path


def _assemble_aspect_variant(
    *,
    label: str,
    width: int,
    height: int,
    storyboard: dict[str, Any],
    shot_sources: list[Path],
    master_audio_wav: Path,
    srt_path: Path,
    out_mp4: Path,
    work_dir: Path,
    burn_subtitles: bool = True,
    fps: int = 24,
) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    conformed_clips: list[Path] = []
    for shot, src_mp4 in zip(storyboard["shots"], shot_sources):
        shot_id = shot["id"]
        dur = float(shot["duration_sec"])
        conformed = work_dir / f"{shot_id}_{label}.mp4"
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},format=yuv420p"
        )
        run_cmd([
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(src_mp4),
            "-t",
            f"{dur:.3f}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-an",
            str(conformed),
        ])
        conformed_clips.append(conformed)

    concat_txt = work_dir / f"concat_{label}.txt"
    concat_txt.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in conformed_clips),
        encoding="utf-8",
    )
    story_video = work_dir / f"story_{label}.mp4"
    run_cmd([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_txt),
        "-c",
        "copy",
        str(story_video),
    ])

    story_with_subs = work_dir / f"story_subtitled_{label}.mp4"
    if burn_subtitles and srt_path.exists():
        local_srt = work_dir / "subs.srt"
        shutil.copy2(srt_path, local_srt)
        is_vertical = height > width
        margin_v = int(height * 0.14) if is_vertical else int(height * 0.06)
        font_size = 18 if is_vertical else 22
        style = (
            f"FontName=Arial,FontSize={font_size},PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BackColour=&H66000000,BorderStyle=3,Outline=1,"
            f"Shadow=0,Alignment=2,MarginV={margin_v}"
        )
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                story_video.name,
                "-vf",
                f"subtitles=subs.srt:force_style='{style}'",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-an",
                story_with_subs.name,
            ],
            cwd=work_dir,
        )
    else:
        shutil.copy2(story_video, story_with_subs)

    story_dur = sum(float(s["duration_sec"]) for s in storyboard["shots"])
    if storyboard["end_card"]["enabled"]:
        end_card_dur = float(storyboard["end_card"]["duration_sec"])
        end_card_clip = _render_end_card_clip(storyboard, width, height, work_dir, fps=fps)
        full_concat = work_dir / f"full_concat_{label}.txt"
        full_concat.write_text(
            f"file '{story_with_subs.resolve().as_posix()}'\nfile '{end_card_clip.resolve().as_posix()}'\n",
            encoding="utf-8",
        )
        full_video = work_dir / f"full_video_{label}.mp4"
        run_cmd([
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(full_concat),
            "-c",
            "copy",
            str(full_video),
        ])
        total_dur = story_dur + end_card_dur
    else:
        full_video = story_with_subs
        total_dur = story_dur

    run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        str(full_video),
        "-i",
        str(master_audio_wav),
        "-af",
        f"apad=whole_dur={total_dur:.3f},atrim=0:{total_dur:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(out_mp4),
    ])
    return out_mp4


def run_assemble_stage(
    config: PipelineConfig,
    *,
    cut_type: str = "final",
    quality: str = "final",
    force: bool = False,
) -> dict[str, Any]:
    """Assemble radio cut, rough cut, or dual-aspect final exports."""
    config.ensure_dirs()
    storyboard, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    narration_wav = config.narration_dir / "narration_full.wav"
    srt_path = config.narration_dir / "subtitles.srt"
    if not narration_wav.exists():
        raise FileNotFoundError(f"Combined narration missing: {narration_wav}. Run narration stage first.")

    story_dur = sum(float(s["duration_sec"]) for s in storyboard["shots"])
    cache = CacheManifest(config.cache_manifest_path)

    if cut_type == "radio":
        work_dir = config.radio_cut_dir / "_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        temp_music = work_dir / "placeholder_temp_track.wav"
        generate_silent_or_tone_wav(temp_music, story_dur, freq_hz=146.83, amplitude=0.06)
        master_audio = _build_master_audio(narration_wav, temp_music, story_dur, work_dir)
        out_mp4 = config.radio_cut_dir / "radio_cut_16x9.mp4"

        input_hash = compute_input_hash({
            "cut_type": "radio",
            "narration_sha256": file_sha256(narration_wav),
            "srt_sha256": file_sha256(srt_path),
            "story_dur": story_dur,
        })
        if cache.is_valid("assemble_radio", "radio", input_hash, [out_mp4], force=force):
            print("[assemble] radio_cut: CACHE HIT")
            return {"outputs": [str(out_mp4)], "cache_hit": True}

        local_srt = work_dir / "subs.srt"
        if srt_path.exists():
            shutil.copy2(srt_path, local_srt)
            vf = "subtitles=subs.srt:force_style='FontName=Arial,FontSize=24,Alignment=2,MarginV=80'"
        else:
            vf = "null"
        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s=1280x720:r=24:d={story_dur:.3f}",
                "-i",
                str(master_audio),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(out_mp4),
            ],
            cwd=work_dir,
        )
        cache.record("assemble_radio", "radio", input_hash, [out_mp4])
        print(f"[assemble] radio_cut: GENERATED -> {out_mp4}")
        return {"outputs": [str(out_mp4)], "cache_hit": False}

    selected_music = config.music_dir / "score_selected.wav"
    if not selected_music.exists():
        raise FileNotFoundError(f"Selected score missing: {selected_music}. Run music stage first.")

    if cut_type == "rough":
        work_dir = config.rough_cut_dir / "_work"
        out_dir = config.rough_cut_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        shot_sources: list[Path] = []
        for shot in storyboard["shots"]:
            kf = config.keyframes_dir / f"{shot['id']}.png"
            if not kf.exists():
                raise FileNotFoundError(f"Keyframe missing: {kf}")
            still_mp4 = work_dir / f"{shot['id']}_still.mp4"
            render_still_or_ken_burns_clip(
                kf,
                still_mp4,
                duration_sec=float(shot["duration_sec"]),
                width=854,
                height=480,
                motion="static",
            )
            shot_sources.append(still_mp4)
    else:
        work_dir = config.final_dir / "_work"
        out_dir = config.final_dir
        shot_sources = []
        for shot in storyboard["shots"]:
            clip = config.shots_dir / f"{shot['id']}.mp4"
            if not clip.exists():
                raise FileNotFoundError(f"Shot clip missing: {clip}. Run shots stage first.")
            shot_sources.append(clip)

    input_hash = compute_input_hash({
        "cut_type": cut_type,
        "quality": quality,
        "narration_sha256": file_sha256(narration_wav),
        "music_sha256": file_sha256(selected_music),
        "srt_sha256": file_sha256(srt_path),
        "end_card": storyboard["end_card"],
        "shots": [
            {"id": s["id"], "duration": s["duration_sec"], "src_sha": file_sha256(p)}
            for s, p in zip(storyboard["shots"], shot_sources)
        ],
    })

    suffix = "_draft" if quality == "draft" else ""
    out_9x16 = out_dir / f"film_9x16{suffix}.mp4"
    out_16x9 = out_dir / f"film_16x9{suffix}.mp4"
    if cache.is_valid(f"assemble_{cut_type}", quality, input_hash, [out_9x16, out_16x9], force=force):
        print(f"[assemble] {cut_type} ({quality}): CACHE HIT")
        return {"outputs": [str(out_9x16), str(out_16x9)], "cache_hit": True}

    work_dir.mkdir(parents=True, exist_ok=True)
    master_audio = _build_master_audio(narration_wav, selected_music, story_dur, work_dir)
    if srt_path.exists():
        shutil.copy2(srt_path, out_dir / "subtitles.srt")

    for label, (fw, fh, dw, dh) in ASPECT_TARGETS.items():
        w, h = (dw, dh) if quality == "draft" else (fw, fh)
        target_file = out_9x16 if label == "9x16" else out_16x9
        _assemble_aspect_variant(
            label=label,
            width=w,
            height=h,
            storyboard=storyboard,
            shot_sources=shot_sources,
            master_audio_wav=master_audio,
            srt_path=srt_path,
            out_mp4=target_file,
            work_dir=work_dir / label,
            burn_subtitles=True,
        )
        print(f"[assemble] Exported {label} ({w}x{h}) -> {target_file}")

    cache.record(f"assemble_{cut_type}", quality, input_hash, [out_9x16, out_16x9])
    return {"outputs": [str(out_9x16), str(out_16x9)], "cache_hit": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble radio cut, rough cut, or final dual-aspect exports.")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--quality", choices=["draft", "final"], default="final")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--radio-cut", action="store_true")
    group.add_argument("--rough-cut", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    cut_type = "radio" if args.radio_cut else ("rough" if args.rough_cut else "final")
    cfg = load_config(root=args.root)
    res = run_assemble_stage(cfg, cut_type=cut_type, quality=args.quality, force=args.force)
    print(f"[assemble] Done ({cut_type}): {res['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
