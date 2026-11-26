"""Tests for storyboard JSON Schema validation, consent gate, caching, retries, and secret redaction."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pipeline.cache import CacheManifest, compute_input_hash
from pipeline.config import PROJECT_ROOT
from pipeline.ffmpeg_utils import wrap_subtitle_text
from pipeline.logger import RunLogger
from pipeline.retry import NonRetryableError, with_retry
from pipeline.schema_validator import StoryboardValidationError, validate_storyboard


def test_default_storyboard_validates() -> None:
    sb, warnings = validate_storyboard(
        PROJECT_ROOT / "storyboard.json",
        PROJECT_ROOT / "schema" / "storyboard.schema.json",
    )
    assert len(sb["shots"]) == 9
    assert all(len(s["reason"]) >= 8 for s in sb["shots"])
    assert warnings == []


def test_consent_gate_blocks_unverified_real_person(tmp_path: Path) -> None:
    sb = json.loads((PROJECT_ROOT / "storyboard.json").read_text(encoding="utf-8"))
    sb["character_sheet"]["is_real_person"] = True
    sb["character_sheet"]["consent_verified"] = False
    sb_path = tmp_path / "storyboard.json"
    sb_path.write_text(json.dumps(sb), encoding="utf-8")

    with pytest.raises(StoryboardValidationError, match="Consent gate blocked"):
        validate_storyboard(sb_path, PROJECT_ROOT / "schema" / "storyboard.schema.json")


def test_schema_rejects_missing_shot_reason(tmp_path: Path) -> None:
    sb = json.loads((PROJECT_ROOT / "storyboard.json").read_text(encoding="utf-8"))
    del sb["shots"][0]["reason"]
    sb_path = tmp_path / "storyboard.json"
    sb_path.write_text(json.dumps(sb), encoding="utf-8")

    with pytest.raises(StoryboardValidationError, match="reason"):
        validate_storyboard(sb_path, PROJECT_ROOT / "schema" / "storyboard.schema.json")


def test_cache_manifest_invalidates_only_changed_item(tmp_path: Path) -> None:
    manifest = CacheManifest(tmp_path / ".cache_manifest.json")
    out1 = tmp_path / "shot_01.png"
    out2 = tmp_path / "shot_02.png"
    out1.write_bytes(b"img1")
    out2.write_bytes(b"img2")

    h1 = compute_input_hash({"prompt": "dawn hills", "seed": 1})
    h2 = compute_input_hash({"prompt": "wooden shop", "seed": 2})
    manifest.record("keyframes", "shot_01", h1, [out1])
    manifest.record("keyframes", "shot_02", h2, [out2])

    assert manifest.is_valid("keyframes", "shot_01", h1, [out1])
    assert manifest.is_valid("keyframes", "shot_02", h2, [out2])

    h1_changed = compute_input_hash({"prompt": "dawn hills golden", "seed": 1})
    assert not manifest.is_valid("keyframes", "shot_01", h1_changed, [out1])
    assert manifest.is_valid("keyframes", "shot_02", h2, [out2])


def test_retry_exponential_and_non_retryable() -> None:
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient 429")
        return "ok"

    assert with_retry(flaky, max_attempts=3, base_delay_s=0.01) == "ok"
    assert attempts == 3

    def fatal() -> str:
        raise NonRetryableError("invalid key")

    with pytest.raises(NonRetryableError):
        with_retry(fatal, max_attempts=3, base_delay_s=0.01)


def test_run_logger_redacts_secrets(tmp_path: Path) -> None:
    log_path = tmp_path / "runs.jsonl"
    logger = RunLogger(log_path, run_id="testrun")
    logger.log_call(
        stage="smoke",
        shot_id=None,
        provider="gemini",
        model="gemini-3.8-flash",
        parameters={"api_key": "super-secret-value", "voice": "Charon"},
        seed=None,
        latency_s=0.1,
    )
    text = log_path.read_text(encoding="utf-8")
    assert "super-secret-value" not in text
    assert "[REDACTED]" in text


def test_subtitle_wrapping_constraints() -> None:
    wrapped = wrap_subtitle_text(
        "This is a much longer subtitle sentence that should wrap cleanly into at most two lines."
    )
    lines = wrapped.splitlines()
    assert len(lines) <= 2
    assert all(len(line) <= 40 for line in lines)


def test_single_shot_edit_regenerates_only_one_shot(tmp_path: Path) -> None:
    from pipeline.config import load_config
    from pipeline.keyframes import run_keyframes_stage
    from pipeline.narration import run_narration_stage

    (tmp_path / "schema").mkdir()
    shutil.copy2(PROJECT_ROOT / "schema" / "storyboard.schema.json", tmp_path / "schema" / "storyboard.schema.json")
    sb_path = tmp_path / "storyboard.json"
    shutil.copy2(PROJECT_ROOT / "storyboard.json", sb_path)

    cfg = load_config(root=tmp_path, mode="mock")
    kf1 = run_keyframes_stage(cfg)
    nar1 = run_narration_stage(cfg)
    assert kf1["regenerated"] == 9 and kf1["cache_hits"] == 0
    assert nar1["regenerated"] == 9 and nar1["cache_hits"] == 0

    calls_before = len(cfg.runs_log_path.read_text(encoding="utf-8").splitlines())

    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    sb["shots"][2]["keyframe_prompt"] = "Close-up of tarnished brass radio dial glowing faintly in warm dust"
    sb["shots"][2]["narration_line"] = "አሮጌው ሬዲዮ ቀስ በቀስ መብራት ጀመረ።"
    sb_path.write_text(json.dumps(sb, indent=2, ensure_ascii=False), encoding="utf-8")

    kf2 = run_keyframes_stage(cfg)
    nar2 = run_narration_stage(cfg)
    assert kf2["regenerated"] == 1 and kf2["cache_hits"] == 8
    assert nar2["regenerated"] == 1 and nar2["cache_hits"] == 8

    all_lines = cfg.runs_log_path.read_text(encoding="utf-8").splitlines()
    new_records = [json.loads(line) for line in all_lines[calls_before:]]
    assert len(new_records) == 2
    assert {r["shot_id"] for r in new_records} == {"shot_03"}
    assert {r["stage"] for r in new_records} == {"keyframes", "narration"}
