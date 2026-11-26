"""FFmpeg, ffprobe, subtitle, audio-mixing, and Pillow visual utilities."""

from __future__ import annotations

import json
import math
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run an external command, raising a readable error on failure."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDERR:\n{proc.stderr[-1500:]}"
        )
    return proc


def probe_media(path: Path) -> dict[str, Any]:
    """Inspect a media file using ffprobe and return parsed JSON."""
    proc = run_cmd([
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ])
    return json.loads(proc.stdout)


def get_duration_sec(path: Path) -> float:
    """Return media duration in seconds using ffprobe."""
    info = probe_media(path)
    return float(info.get("format", {}).get("duration", 0.0))


def wrap_subtitle_text(text: str, max_chars: int = 40, max_lines: int = 2) -> str:
    """Wrap subtitle text cleanly into at most 2 lines of ~40 characters."""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return ""
    lines = textwrap.wrap(cleaned, width=max_chars, break_long_words=False)
    if len(lines) <= max_lines:
        return "\n".join(lines)
    kept = lines[: max_lines - 1]
    remainder = " ".join(lines[max_lines - 1 :])
    if len(remainder) > max_chars:
        remainder = remainder[: max_chars - 3].rstrip() + "..."
    kept.append(remainder)
    return "\n".join(kept)


def format_srt_timestamp(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(entries: list[tuple[float, float, str]], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for idx, (start, end, text) in enumerate(entries, start=1):
        wrapped = wrap_subtitle_text(text)
        if not wrapped:
            continue
        blocks.append(
            f"{idx}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n{wrapped}\n"
        )
    out_path.write_text("\n".join(blocks), encoding="utf-8")
    return out_path


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        p = Path(candidate)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def generate_mock_reference_sheet(
    out_path: Path,
    *,
    character_name: str,
    description: str,
    seed: int = 0,
) -> Path:
    """Create a deterministic 3-panel character & style reference sheet for offline runs."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 1024, 576
    img = Image.new("RGB", (w, h), (34, 30, 26))
    draw = ImageDraw.Draw(img)
    font_title = _load_font(26)
    font_sub = _load_font(16)

    panels = ["FRONT", "3/4 PROFILE", "EXPRESSION"]
    panel_w = (w - 80) // 3
    for i, label in enumerate(panels):
        x0 = 20 + i * (panel_w + 20)
        y0, x1, y1 = 80, x0 + panel_w, h - 90
        shade = 56 + ((seed + i * 17) % 25)
        draw.rectangle([x0, y0, x1, y1], fill=(shade + 25, shade + 10, shade - 5), outline=(215, 175, 110), width=3)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        r = min(panel_w, y1 - y0) // 4
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(225, 190, 140), outline=(245, 225, 185), width=3)
        draw.text((cx, y1 - 24), label, fill=(245, 238, 225), font=font_sub, anchor="mm")

    draw.text((w // 2, 38), f"CHARACTER SHEET: {character_name}", fill=(245, 220, 165), font=font_title, anchor="mm")
    desc_short = (description[:96] + "...") if len(description) > 96 else description
    draw.text((w // 2, h - 42), desc_short, fill=(210, 205, 195), font=font_sub, anchor="mm")
    img.save(out_path, format="PNG")
    return out_path


def generate_mock_keyframe(
    out_path: Path,
    *,
    shot_id: str,
    scene: str,
    shot_size: str,
    prompt: str,
    seed: int = 0,
    width: int = 1280,
    height: int = 720,
) -> Path:
    """Create a deterministic warm-toned centered keyframe image for offline/mock runs."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r_base = 42 + (seed * 37) % 55
    g_base = 34 + (seed * 53) % 45
    b_base = 28 + (seed * 29) % 35
    img = Image.new("RGB", (width, height), (r_base, g_base, b_base))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        t = y / max(1, height - 1)
        wave = 0.45 * math.sin(t * math.pi)
        r = max(0, min(255, int(r_base + (210 - r_base) * wave)))
        g = max(0, min(255, int(g_base + (155 - g_base) * wave)))
        b = max(0, min(255, int(b_base + (95 - b_base) * wave)))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    cx, cy = width // 2, height // 2
    radius = min(width, height) // 5
    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        fill=(232, 194, 132),
        outline=(252, 235, 198),
        width=4,
    )

    font_lg = _load_font(max(24, width // 30))
    font_sm = _load_font(max(16, width // 52))
    draw.text((cx, int(height * 0.16)), f"{shot_id.upper()} - {scene}", fill=(252, 246, 236), font=font_lg, anchor="mm")
    draw.text((cx, int(height * 0.80)), f"[{shot_size}] {prompt[:64]}", fill=(242, 232, 218), font=font_sm, anchor="mm")
    img.save(out_path, format="PNG")
    return out_path


def render_end_card_image(
    title: str,
    disclosure_text: str,
    credits: str,
    width: int,
    height: int,
    out_path: Path,
) -> Path:
    """Create the mandatory visible AI disclosure end card image."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), (18, 17, 16))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(max(28, min(width, height) // 18))
    disc_font = _load_font(max(18, min(width, height) // 30))
    cred_font = _load_font(max(14, min(width, height) // 40))

    cx = width // 2
    wrap_w = 34 if width < height else 68
    draw.text((cx, int(height * 0.34)), title, fill=(246, 238, 222), font=title_font, anchor="mm")
    disc_wrapped = "\n".join(textwrap.wrap(disclosure_text, width=wrap_w))
    draw.multiline_text(
        (cx, int(height * 0.50)),
        disc_wrapped,
        fill=(230, 178, 92),
        font=disc_font,
        anchor="mm",
        align="center",
    )
    if credits:
        cred_wrapped = "\n".join(textwrap.wrap(credits, width=wrap_w))
        draw.multiline_text(
            (cx, int(height * 0.67)),
            cred_wrapped,
            fill=(185, 180, 172),
            font=cred_font,
            anchor="mm",
            align="center",
        )
    img.save(out_path, format="PNG")
    return out_path


def _motion_to_zoompan(camera_movement: str, frames: int) -> tuple[str, str, str]:
    if camera_movement == "static":
        return "1.0", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if camera_movement in ("slow_pull_out", "zoom_out"):
        return f"max(1.0,1.12-0.12*(on/{frames}))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if camera_movement == "pan_left":
        return "1.10", f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"
    if camera_movement == "pan_right":
        return "1.10", f"(iw-iw/zoom)*(on/{frames})", "ih/2-(ih/zoom/2)"
    if camera_movement == "tilt_up":
        return "1.10", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{frames})"
    if camera_movement == "tilt_down":
        return "1.10", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(on/{frames})"
    # slow_push_in / dolly_in / ken_burns
    return f"min(1.12,1.0+0.12*(on/{frames}))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"


def render_still_or_ken_burns_clip(
    image_path: Path,
    out_path: Path,
    duration_sec: float,
    width: int,
    height: int,
    motion: str = "slow_push_in",
    fps: int = 24,
) -> Path:
    """Animate a keyframe still using FFmpeg zoompan (Ken Burns fallback) at constant fps."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(2, int(round(duration_sec * fps)))
    z_expr, x_expr, y_expr = _motion_to_zoompan(motion, frames)

    up_w, up_h = width * 2, height * 2
    vf = (
        f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
        f"crop={up_w}:{up_h},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )
    run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        f"{duration_sec:.3f}",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-an",
        str(out_path),
    ])
    return out_path


def generate_silent_or_tone_wav(
    out_path: Path,
    duration_sec: float,
    freq_hz: float = 0.0,
    amplitude: float = 0.04,
    sample_rate: int = 48000,
) -> Path:
    """Generate deterministic silence or gentle harmonic underscore WAV via FFmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if freq_hz <= 0.0:
        src = f"anullsrc=channel_layout=stereo:sample_rate={sample_rate}"
        af = "anull"
    else:
        f2 = round(freq_hz * 1.1892, 2)
        f3 = round(freq_hz * 1.4983, 2)
        src = f"sine=frequency={freq_hz}:sample_rate={sample_rate}:duration={duration_sec:.3f}"
        af = (
            f"aeval=val(0)*0.4+0.3*sin(2*PI*{f2}*t)+0.25*sin(2*PI*{f3}*t):c=stereo,"
            f"lowpass=f=950,"
            f"volume={amplitude},"
            f"afade=t=in:st=0:d=0.6,"
            f"afade=t=out:st={max(0.0, duration_sec - 0.8):.3f}:d=0.8"
        )
    run_cmd([
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        src,
        "-t",
        f"{duration_sec:.3f}",
        "-af",
        af,
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(out_path),
    ])
    return out_path


def normalize_stem(src: Path, dst: Path, target_i: float = -23.0, sample_rate: int = 48000) -> Path:
    """Bring an audio stem to a consistent baseline level before mixing."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        f"aformat=sample_rates={sample_rate}:channel_layouts=stereo,loudnorm=I={target_i}:TP=-2:LRA=11",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(dst),
    ])
    return dst


def concat_shot_narrations(
    segments: list[tuple[Path, float]],
    out_wav: Path,
    work_dir: Path,
    sample_rate: int = 48000,
) -> Path:
    """Pad or trim each shot's narration WAV to its exact shot slot and concatenate."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    padded_files: list[Path] = []
    for idx, (wav_path, slot_dur) in enumerate(segments):
        slot_wav = work_dir / f"nar_slot_{idx:02d}.wav"
        run_cmd([
            "ffmpeg",
            "-y",
            "-i",
            str(wav_path),
            "-af",
            f"aformat=sample_rates={sample_rate}:channel_layouts=stereo,apad=whole_dur={slot_dur:.3f},atrim=0:{slot_dur:.3f}",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            str(slot_wav),
        ])
        padded_files.append(slot_wav)

    concat_txt = work_dir / "narration_concat.txt"
    concat_txt.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in padded_files),
        encoding="utf-8",
    )
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
        str(out_wav),
    ])
    return out_wav


def mix_with_sidechain_ducking(
    narration_wav: Path,
    music_wav: Path,
    out_wav: Path,
    total_duration_sec: float,
    sample_rate: int = 48000,
) -> Path:
    """Duck music under narration with FFmpeg sidechaincompress (threshold=0.02, ratio=6, attack=300, release=1500)."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"[0:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
        f"apad=whole_dur={total_duration_sec:.3f},atrim=0:{total_duration_sec:.3f},asplit=2[voice][sc];"
        f"[1:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
        f"aloop=loop=-1:size=2e+09,atrim=0:{total_duration_sec:.3f},volume=0.38[bgm];"
        f"[bgm][sc]sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500[ducked];"
        f"[voice][ducked]amix=inputs=2:duration=first:weights=1 1:normalize=0[mix]"
    )
    run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        str(narration_wav),
        "-i",
        str(music_wav),
        "-filter_complex",
        filter_complex,
        "-map",
        "[mix]",
        "-t",
        f"{total_duration_sec:.3f}",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(out_wav),
    ])
    return out_wav


def two_pass_loudnorm(
    src_wav: Path,
    dst_wav: Path,
    target_i: float = -14.0,
    target_tp: float = -1.0,
    target_lra: float = 11.0,
    sample_rate: int = 48000,
) -> Path:
    """Two-pass EBU R128 loudness normalisation targeting -14 LUFS and -1 dBTP."""
    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    pass1 = run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        str(src_wav),
        "-af",
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
        "-f",
        "null",
        "-",
    ])
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", pass1.stderr, re.DOTALL)
    if match:
        stats = json.loads(match.group(0))
        if all(
            str(stats.get(k, "-inf")) != "-inf"
            for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
        ):
            af = (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
                f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
                f"offset={stats['target_offset']}:linear=true"
            )
            run_cmd([
                "ffmpeg",
                "-y",
                "-i",
                str(src_wav),
                "-af",
                af,
                "-ar",
                str(sample_rate),
                "-ac",
                "2",
                str(dst_wav),
            ])
            return dst_wav

    run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        str(src_wav),
        "-af",
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(dst_wav),
    ])
    return dst_wav
