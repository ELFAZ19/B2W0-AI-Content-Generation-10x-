"""Generate a narrated 16:9 Python codebase walkthrough video using Pillow, Gemini TTS, and FFmpeg."""

from __future__ import annotations

import base64
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.config import DEFAULT_GEMINI_TTS_MODEL, load_config
from pipeline.ffmpeg_utils import get_duration_sec, normalize_stem, run_cmd
from pipeline.retry import with_retry

SLIDES: list[dict[str, str]] = [
    {
        "id": "slide_01",
        "title": "1. Project Overview & Entry Point (pipeline/__main__.py)",
        "code": (
            "# Single command runs all 6 stages deterministically:\n"
            "$ python -m pipeline run --mode auto\n\n"
            "def run_full_pipeline(config, quality='final', force=False):\n"
            "    validate_storyboard(config.storyboard_path, config.schema_path)\n"
            "    script.run_script_stage(config, force=force)\n"
            "    narration.run_narration_stage(config, force=force)\n"
            "    keyframes.run_keyframes_stage(config, force=force)\n"
            "    shots.run_shots_stage(config, quality=quality, force=force)\n"
            "    music.run_music_stage(config, force=force)\n"
            "    assemble.run_assemble_stage(config, cut_type='final')"
        ),
        "narration": (
            "Welcome to the Python walkthrough of the Heritage Short AI video pipeline. "
            "Everything starts in pipeline slash main dot py, where a single CLI command "
            "validates the storyboard contract and orchestrates six deterministic stages: "
            "script, narration, keyframes, shots, music, and final dual-aspect assembly."
        ),
    },
    {
        "id": "slide_02",
        "title": "2. Storyboard Contract & Consent Gate (schema_validator.py)",
        "code": (
            "# schema/storyboard.schema.json (JSON Schema Draft 2020-12)\n"
            "def validate_storyboard(storyboard_path, schema_path):\n"
            "    # 1. Validate required fields, 60-90s duration, ai_disclosure\n"
            "    # 2. Enforce consent gate for real people & cloned voices:\n"
            "    if char['is_real_person'] and not char['consent_verified']:\n"
            "        raise StoryboardValidationError('Consent required!')\n"
            "    if nar['is_cloned_voice'] and not nar['consent_verified']:\n"
            "        raise StoryboardValidationError('Voice consent required!')"
        ),
        "narration": (
            "Stage one uses schema validator dot py to validate storyboard dot json against "
            "a strict Draft 2020-12 JSON schema. It checks shot durations, requires AI "
            "disclosure, and enforces a hard consent gate blocking unverified real-person "
            "likenesses or cloned voices before any API call is made."
        ),
    },
    {
        "id": "slide_03",
        "title": "3. Keyframes & Content-Addressed Cache (keyframes.py, cache.py)",
        "code": (
            "# Cloudflare Workers AI: FLUX.2 klein (multipart/form-data)\n"
            "if 'flux-2' in model:\n"
            "    files = {'prompt': (None, prompt), 'steps': (None, '4'), ...}\n"
            "    resp = requests.post(url, headers=headers, files=files)\n\n"
            "# SHA-256 cache manifest avoids re-paying or re-generating:\n"
            "input_hash = compute_input_hash({'prompt': prompt, 'seed': seed})\n"
            "if cache.is_valid('keyframes', shot_id, input_hash, [out_png]):\n"
            "    print(f'[keyframes] {shot_id}: CACHE HIT')"
        ),
        "narration": (
            "Stage two in keyframes dot py generates a character reference sheet and nine "
            "keyframes using Cloudflare FLUX. Each call is keyed by a SHA-256 hash in "
            "cache dot py, so editing one shot only regenerates that single shot while "
            "all unchanged shots stay cached."
        ),
    },
    {
        "id": "slide_04",
        "title": "4. Amharic Narration & Subtitles (narration.py)",
        "code": (
            "# Gemini 3.8 Flash TTS via Interactions API (v1beta)\n"
            "interaction = client.interactions.create(\n"
            "    model='gemini-3.8-flash-tts',\n"
            "    input=[{'type': 'user_input', 'content': [{'type': 'text',\n"
            "        'text': shot['narration_line'],\n"
            "        'annotations': [{'type': 'speech_metadata', 'style': style}]}]}],\n"
            "    response_format={'type': 'audio'},\n"
            "    generation_config={'speech_config': [{'voice': 'Charon'}]},\n"
            ")"
        ),
        "narration": (
            "Stage three in narration dot py calls Gemini 3.8 Flash TTS for each Amharic line, "
            "normalizes each stem to minus 18 LUFS, pads it to match the shot duration, "
            "and writes synchronized English subtitles to subtitles dot srt."
        ),
    },
    {
        "id": "slide_05",
        "title": "5. Motion & Dual-Aspect Assembly (shots.py, assemble.py)",
        "code": (
            "# shots.py: Kaggle Wan 2.2 clips OR FFmpeg Ken Burns fallback\n"
            "# music.py: Kaggle ACE-Step 1.5 OR FFmpeg underscore fallback\n\n"
            "# assemble.py: sidechain ducking + 2-pass -14 LUFS + end card\n"
            "mix_with_sidechain_ducking(narration_wav, music_wav, ducked_wav, dur)\n"
            "two_pass_loudnorm(ducked_wav, norm_wav, target_i=-14.0, target_tp=-1.0)\n"
            "# Exports both 9:16 (1080x1920) and 16:9 (1920x1080) MP4s"
        ),
        "narration": (
            "Stages four through six conform moving shots from Wan 2.2 or Ken Burns, "
            "duck background music under the voiceover using FFmpeg sidechain compression, "
            "normalize to minus 14 LUFS, burn subtitles, append the Made with AI end card, "
            "and export both 9 by 16 and 16 by 9 MP4s."
        ),
    },
]


def _render_slide(slide: dict[str, str], out_png: Path) -> None:
    w, h = 1920, 1080
    img = Image.new("RGB", (w, h), (16, 20, 28))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 44)
        font_code = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 28)
        font_sub = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 24)
    except OSError:
        font_title = ImageFont.load_default()
        font_code = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Header bar
    draw.rectangle([0, 0, w, 120], fill=(24, 31, 44))
    draw.text((70, 36), slide["title"], fill=(245, 196, 81), font=font_title)

    # Code panel
    draw.rounded_rectangle([70, 160, w - 70, 790], radius=18, fill=(24, 28, 38), outline=(58, 70, 92), width=2)
    y = 200
    for line in slide["code"].splitlines():
        color = (130, 170, 255) if line.strip().startswith("#") or line.strip().startswith("$") else (230, 237, 243)
        draw.text((110, y), line, fill=color, font=font_code)
        y += 42

    # Narration caption box
    draw.rounded_rectangle([70, 825, w - 70, 1020], radius=14, fill=(20, 25, 34), outline=(45, 55, 72), width=1)
    wrapped = textwrap.wrap(slide["narration"], width=110)
    cy = 850
    for wline in wrapped[:4]:
        draw.text((100, cy), wline, fill=(205, 214, 224), font=font_sub)
        cy += 36

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def _tts_windows_sapi(text: str, out_wav: Path) -> None:
    import subprocess
    raw = out_wav.with_suffix(".raw.wav")
    raw.parent.mkdir(parents=True, exist_ok=True)
    safe_text = text.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{raw.resolve()}'); "
        f"$s.Speak('{safe_text}'); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    normalize_stem(raw, out_wav, target_i=-16.0)
    raw.unlink(missing_ok=True)


def _tts_slide(api_key: str, text: str, out_wav: Path) -> None:
    from google import genai

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta", "timeout": 45})

    def _call():
        return client.interactions.create(
            model=DEFAULT_GEMINI_TTS_MODEL,
            input=[
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [
                                {"type": "speech_metadata", "style": "Clear, friendly technical walkthrough narrator"}
                            ],
                        }
                    ],
                }
            ],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": "Charon"}]},
        )

    try:
        resp = with_retry(_call, max_attempts=2)
        raw = out_wav.with_suffix(".raw.wav")
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(base64.b64decode(resp.output_audio.data))
        normalize_stem(raw, out_wav, target_i=-16.0)
        raw.unlink(missing_ok=True)
    except Exception as exc:
        print(f"[walkthrough] Gemini TTS failed ({exc}); falling back to Windows SAPI TTS.", flush=True)
        _tts_windows_sapi(text, out_wav)


def main() -> int:
    cfg = load_config(mode="live")
    assert cfg.gemini_api_key, "GEMINI_API_KEY is required"

    work_dir = cfg.outputs_dir / "walkthrough" / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = cfg.outputs_dir / "walkthrough" / "python_walkthrough_16x9.mp4"

    clips: list[Path] = []
    for slide in SLIDES:
        sid = slide["id"]
        png = work_dir / f"{sid}.png"
        wav = work_dir / f"{sid}.wav"
        clip = work_dir / f"{sid}.mp4"
        _render_slide(slide, png)
        if not wav.exists():
            _tts_slide(cfg.gemini_api_key, slide["narration"], wav)
        dur = get_duration_sec(wav) + 0.6
        run_cmd([
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(png),
            "-i",
            str(wav),
            "-af",
            f"apad=whole_dur={dur:.3f},atrim=0:{dur:.3f}",
            "-t",
            f"{dur:.3f}",
            "-vf",
            "fps=24,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(clip),
        ])
        clips.append(clip)
        print(f"[walkthrough] {sid}: {dur:.2f}s", flush=True)

    concat_txt = work_dir / "concat.txt"
    concat_txt.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
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
        str(out_mp4),
    ])
    print(f"[walkthrough] Exported -> {out_mp4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
