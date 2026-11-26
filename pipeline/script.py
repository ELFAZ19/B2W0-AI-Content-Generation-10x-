"""Stage 1: Storyboard validation, generation, and translation via Gemini 3.8 Flash."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from pipeline.cache import CacheManifest, compute_input_hash, file_sha256
from pipeline.config import (
    DEFAULT_GEMINI_LITE_MODEL,
    DEFAULT_GEMINI_TEXT_MODEL,
    PipelineConfig,
    load_config,
)
from pipeline.logger import RunLogger
from pipeline.retry import with_retry
from pipeline.schema_validator import load_json, validate_storyboard


def _extract_json_block(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    return json.loads(cleaned)


def generate_storyboard_from_brief(
    config: PipelineConfig,
    brief: str,
    language: str = "Amharic",
    language_code: str = "am-ET",
) -> dict[str, Any]:
    """Use Gemini 3.8 Flash (live) to draft a schema-valid storyboard.json from a brief."""
    if not config.has_gemini:
        raise RuntimeError("GEMINI_API_KEY is required to generate a new storyboard from a brief.")

    from google import genai

    schema = load_json(config.schema_path)
    prompt = (
        "Create a complete, culturally grounded 60-90 second short film storyboard JSON "
        "matching the exact JSON Schema below.\n"
        f"Story brief: {brief}\n"
        f"Narration language: {language} ({language_code})\n"
        "English subtitles must be <= 2 lines per shot and <= 40 characters per line.\n"
        "Include 8 to 10 shots with varied shot sizes, clear per-shot reasons, centered compositions, "
        "a consistent style_block, character_sheet, and 3 music cues.\n\n"
        f"JSON Schema:\n{json.dumps(schema, indent=2)}"
    )

    client = genai.Client(api_key=config.gemini_api_key, http_options={"api_version": "v1beta"})
    logger = RunLogger(config.runs_log_path)

    t0 = time.perf_counter()

    def _call() -> dict[str, Any]:
        interaction = client.interactions.create(
            model=DEFAULT_GEMINI_TEXT_MODEL,
            input=prompt,
        )
        return _extract_json_block(interaction.output_text or "")

    try:
        storyboard = with_retry(_call, max_attempts=3)
        dt = time.perf_counter() - t0
        with config.storyboard_path.open("w", encoding="utf-8") as fh:
            json.dump(storyboard, fh, indent=2, ensure_ascii=False)
        validated, _ = validate_storyboard(config.storyboard_path, config.schema_path)
        logger.log_call(
            stage="script",
            shot_id=None,
            provider="gemini",
            model=DEFAULT_GEMINI_TEXT_MODEL,
            parameters={"action": "generate_storyboard", "language": language},
            seed=None,
            latency_s=dt,
            status="ok",
            outputs=[str(config.storyboard_path)],
        )
        return validated
    except Exception as exc:
        logger.log_call(
            stage="script",
            shot_id=None,
            provider="gemini",
            model=DEFAULT_GEMINI_TEXT_MODEL,
            parameters={"action": "generate_storyboard", "language": language},
            seed=None,
            latency_s=time.perf_counter() - t0,
            status="error",
            error=str(exc),
        )
        raise


def translate_subtitles(config: PipelineConfig) -> dict[str, Any]:
    """Optionally refresh English subtitles using Gemini 3.5 Flash-Lite."""
    storyboard, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    if not config.has_gemini or config.mode == "mock":
        return storyboard

    from google import genai

    client = genai.Client(api_key=config.gemini_api_key, http_options={"api_version": "v1beta"})
    logger = RunLogger(config.runs_log_path)
    shots = storyboard["shots"]

    lines_payload = [{"id": s["id"], "narration_line": s["narration_line"]} for s in shots]
    prompt = (
        f"Translate these {storyboard['project']['language']} narration lines to natural English subtitles. "
        "Return JSON mapping shot id -> subtitle string. Each subtitle must have at most 2 lines "
        "(separated by \\n) and at most 40 characters per line.\n\n"
        f"{json.dumps(lines_payload, ensure_ascii=False)}"
    )
    t0 = time.perf_counter()
    resp = with_retry(
        lambda: client.interactions.create(model=DEFAULT_GEMINI_LITE_MODEL, input=prompt),
        max_attempts=3,
    )
    dt = time.perf_counter() - t0
    mapping = _extract_json_block(resp.output_text or "{}")
    for shot in shots:
        if shot["id"] in mapping and isinstance(mapping[shot["id"]], str):
            shot["subtitle_en"] = mapping[shot["id"]].strip()

    with config.storyboard_path.open("w", encoding="utf-8") as fh:
        json.dump(storyboard, fh, indent=2, ensure_ascii=False)
    validated, _ = validate_storyboard(config.storyboard_path, config.schema_path)
    logger.log_call(
        stage="script",
        shot_id=None,
        provider="gemini",
        model=DEFAULT_GEMINI_LITE_MODEL,
        parameters={"action": "translate_subtitles", "shots": len(shots)},
        seed=None,
        latency_s=dt,
        status="ok",
    )
    return validated


def run_script_stage(config: PipelineConfig, force: bool = False) -> Path:
    """Validate storyboard.json and write outputs/script/storyboard_summary.json."""
    t0 = time.perf_counter()
    storyboard, warnings = validate_storyboard(config.storyboard_path, config.schema_path)
    out_dir = config.outputs_dir / "script"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "storyboard_summary.json"

    input_hash = compute_input_hash(
        {
            "storyboard_sha256": file_sha256(config.storyboard_path),
            "schema_sha256": file_sha256(config.schema_path),
        }
    )
    cache = CacheManifest(config.cache_manifest_path)
    logger = RunLogger(config.runs_log_path)

    if cache.is_valid("script", "summary", input_hash, [summary_path], force=force):
        logger.log_call(
            stage="script",
            shot_id=None,
            provider="local",
            model="jsonschema-validator",
            parameters={"warnings": len(warnings)},
            seed=None,
            latency_s=time.perf_counter() - t0,
            cache_hit=True,
            input_hash=input_hash,
            status="ok",
            outputs=[str(summary_path)],
        )
        return summary_path

    shots = storyboard["shots"]
    total_duration = sum(float(s["duration_sec"]) for s in shots)
    total_words = sum(len(s["narration_line"].split()) for s in shots)
    summary = {
        "title": storyboard["project"]["title"],
        "language": storyboard["project"]["language"],
        "shot_count": len(shots),
        "total_duration_sec": round(total_duration, 2),
        "total_narration_words": total_words,
        "warnings": warnings,
        "shots": [
            {
                "id": s["id"],
                "duration_sec": s["duration_sec"],
                "shot_size": s["shot_size"],
                "camera_movement": s["camera_movement"],
                "word_count": len(s["narration_line"].split()),
                "reason": s["reason"],
            }
            for s in shots
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    cache.record("script", "summary", input_hash, [summary_path], metadata={"shots": len(shots)})
    logger.log_call(
        stage="script",
        shot_id=None,
        provider="local",
        model="jsonschema-validator",
        parameters={"shot_count": len(shots), "total_duration_sec": round(total_duration, 2)},
        seed=None,
        latency_s=time.perf_counter() - t0,
        cache_hit=False,
        input_hash=input_hash,
        status="ok",
        outputs=[str(summary_path)],
    )
    return summary_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1: validate/generate/translate storyboard.")
    parser.add_argument("--mode", choices=["auto", "live", "mock"], default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--brief", type=str, default=None, help="Generate storyboard.json from brief.")
    parser.add_argument("--language", type=str, default="Amharic")
    parser.add_argument("--language-code", type=str, default="am-ET")
    parser.add_argument("--translate-subtitles", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(root=args.root, mode=args.mode)
    if args.brief:
        generate_storyboard_from_brief(cfg, args.brief, args.language, args.language_code)
    if args.translate_subtitles:
        translate_subtitles(cfg)
    summary = run_script_stage(cfg, force=args.force)
    print(f"[script] validated storyboard -> {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
