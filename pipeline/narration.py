"""Stage 3: Per-shot narration generation with Gemini 3.8 Flash TTS + SRT timing."""

from __future__ import annotations

import argparse
import base64
import time
from pathlib import Path
from typing import Any

from pipeline.cache import CacheManifest, compute_input_hash
from pipeline.config import DEFAULT_GEMINI_TTS_MODEL, PipelineConfig, load_config
from pipeline.ffmpeg_utils import (
    generate_silent_or_tone_wav,
    get_duration_sec,
    normalize_stem,
    run_cmd,
    write_srt,
)
from pipeline.logger import RunLogger
from pipeline.retry import NonRetryableError, with_retry
from pipeline.schema_validator import validate_storyboard


def _synthesize_gemini_tts(
    *,
    api_key: str,
    model: str,
    text: str,
    voice: str,
    style: str,
    out_wav: Path,
) -> float:
    """Call Gemini 3.8 Flash TTS via Interactions API and save WAV directly."""
    from google import genai

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    t0 = time.perf_counter()

    def _call() -> Any:
        try:
            return client.interactions.create(
                model=model,
                input=[
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": text,
                                "annotations": [
                                    {
                                        "type": "speech_metadata",
                                        "style": style,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": voice}]},
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "api key" in msg or "401" in msg or "403" in msg:
                raise NonRetryableError(str(exc)) from exc
            raise

    interaction = with_retry(_call, max_attempts=3)
    latency_s = time.perf_counter() - t0
    if not interaction.output_audio or not interaction.output_audio.data:
        raise RuntimeError("Gemini TTS response contained no audio payload.")

    raw_wav = out_wav.with_suffix(".raw.wav")
    raw_wav.parent.mkdir(parents=True, exist_ok=True)
    raw_wav.write_bytes(base64.b64decode(interaction.output_audio.data))
    normalize_stem(raw_wav, out_wav, target_i=-18.0)
    raw_wav.unlink(missing_ok=True)
    return latency_s


def _synthesize_mock_tts(text: str, duration_sec: float, out_wav: Path, seed: int) -> float:
    """Deterministic offline spoken-cadence placeholder WAV for radio-cut / CI testing."""
    t0 = time.perf_counter()
    speech_dur = max(1.5, min(duration_sec - 0.6, max(2.0, len(text.split()) * 0.42)))
    tone_hz = 190.0 + (seed % 7) * 18.0
    raw_wav = out_wav.with_suffix(".raw.wav")
    generate_silent_or_tone_wav(raw_wav, speech_dur, freq_hz=tone_hz, amplitude=0.14)
    normalize_stem(raw_wav, out_wav, target_i=-18.0)
    raw_wav.unlink(missing_ok=True)
    return time.perf_counter() - t0


def run_narration_stage(
    config: PipelineConfig,
    *,
    shot_filter: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate one WAV per shot (cached by input hash) plus combined narration & subtitles.srt."""
    config.ensure_dirs()
    storyboard, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    narration_cfg = storyboard["narration"]
    cache = CacheManifest(config.cache_manifest_path)
    logger = RunLogger(config.runs_log_path)

    use_live = (
        narration_cfg["provider"] == "gemini-tts"
        and config.resolve_provider(config.has_gemini, "Gemini TTS") == "live"
    )
    provider_tag = "gemini" if use_live else "mock"
    model_tag = DEFAULT_GEMINI_TTS_MODEL if use_live else "mock-tts"

    shot_audio_files: list[Path] = []
    padded_segments: list[Path] = []
    srt_entries: list[tuple[float, float, str]] = []
    cursor_sec = 0.0
    hits = 0
    regenerated = 0

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        shot_dur = float(shot["duration_sec"])
        out_wav = config.narration_dir / f"{shot_id}.wav"
        padded_wav = config.narration_dir / f"{shot_id}_aligned.wav"

        input_hash = compute_input_hash(
            {
                "shot_id": shot_id,
                "narration_line": shot["narration_line"],
                "model": model_tag,
                "voice": narration_cfg["voice"],
                "style_instruction": narration_cfg["style_instruction"],
                "language_code": narration_cfg["language_code"],
                "provider": provider_tag,
                "duration_sec_for_mock": shot_dur if not use_live else None,
            }
        )

        if shot_filter and shot_id != shot_filter:
            if out_wav.exists() and padded_wav.exists():
                speech_dur = get_duration_sec(out_wav)
                shot_audio_files.append(out_wav)
                padded_segments.append(padded_wav)
                sub_end = cursor_sec + min(shot_dur - 0.15, max(1.2, speech_dur))
                srt_entries.append((cursor_sec + 0.05, sub_end, shot["subtitle_en"]))
                cursor_sec += shot_dur
            continue

        if cache.is_valid("narration", shot_id, input_hash, [out_wav], force=force):
            hits += 1
            print(f"[narration] {shot_id}: CACHE HIT")
        else:
            if use_live:
                assert config.gemini_api_key is not None
                latency_s = _synthesize_gemini_tts(
                    api_key=config.gemini_api_key,
                    model=DEFAULT_GEMINI_TTS_MODEL,
                    text=shot["narration_line"],
                    voice=narration_cfg["voice"],
                    style=narration_cfg["style_instruction"],
                    out_wav=out_wav,
                )
            else:
                latency_s = _synthesize_mock_tts(
                    shot["narration_line"], shot_dur, out_wav, int(shot["seed"])
                )

            actual_dur = get_duration_sec(out_wav)
            cache.record(
                "narration",
                shot_id,
                input_hash,
                [out_wav],
                metadata={"duration_sec": actual_dur, "model": model_tag},
            )
            logger.log_call(
                stage="narration",
                shot_id=shot_id,
                provider=provider_tag,
                model=model_tag,
                parameters={
                    "voice": narration_cfg["voice"],
                    "style": narration_cfg["style_instruction"],
                    "language_code": narration_cfg["language_code"],
                    "chars": len(shot["narration_line"]),
                    "audio_duration_sec": round(actual_dur, 3),
                },
                seed=int(shot["seed"]),
                latency_s=latency_s,
                cache_hit=False,
                input_hash=input_hash,
                status="ok",
                outputs=[str(out_wav)],
            )
            regenerated += 1
            print(f"[narration] {shot_id}: GENERATED ({model_tag}, {actual_dur:.2f}s)")

        shot_audio_files.append(out_wav)
        speech_dur = get_duration_sec(out_wav)
        if speech_dur > shot_dur:
            print(
                f"[narration] WARNING: {shot_id} TTS ({speech_dur:.2f}s) exceeds shot duration ({shot_dur:.2f}s)."
            )

        run_cmd([
            "ffmpeg",
            "-y",
            "-i",
            str(out_wav),
            "-af",
            f"aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={shot_dur:.3f},atrim=0:{shot_dur:.3f}",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(padded_wav),
        ])
        padded_segments.append(padded_wav)

        sub_end = cursor_sec + min(shot_dur - 0.15, max(1.2, speech_dur))
        srt_entries.append((cursor_sec + 0.05, sub_end, shot["subtitle_en"]))
        cursor_sec += shot_dur

    combined_wav = config.narration_dir / "narration_full.wav"
    srt_path = config.narration_dir / "subtitles.srt"
    if padded_segments and len(padded_segments) == len(storyboard["shots"]):
        concat_list = config.narration_dir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in padded_segments),
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
            str(concat_list),
            "-c:a",
            "pcm_s16le",
            str(combined_wav),
        ])
        write_srt(srt_entries, srt_path)

    return {
        "cache_hits": hits,
        "regenerated": regenerated,
        "combined_wav": str(combined_wav),
        "srt_path": str(srt_path),
        "total_duration_sec": round(cursor_sec, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate per-shot narration and SRT subtitles.")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    parser.add_argument("--shot", type=str, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(root=args.root, mode=args.mode)
    res = run_narration_stage(cfg, shot_filter=args.shot, force=args.force)
    print(f"[narration] Done: {res['regenerated']} generated, {res['cache_hits']} cached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
