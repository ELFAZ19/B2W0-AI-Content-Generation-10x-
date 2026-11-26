"""JSON Schema, semantic, and ethical consent-gate validation for storyboard.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class StoryboardValidationError(ValueError):
    """Raised when storyboard.json violates schema, consent gate, or production invariants."""


def load_json(path: Path) -> dict[str, Any]:
    """Read and parse a UTF-8 JSON file."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_storyboard(
    storyboard_path: Path,
    schema_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    """Validate storyboard.json against schema, consent gate, and semantic rules."""
    if not schema_path.exists():
        raise StoryboardValidationError(f"Schema file not found: {schema_path}")
    if not storyboard_path.exists():
        raise StoryboardValidationError(f"Storyboard file not found: {storyboard_path}")

    try:
        schema = load_json(schema_path)
        storyboard = load_json(storyboard_path)
    except json.JSONDecodeError as exc:
        raise StoryboardValidationError(f"Invalid JSON in {storyboard_path}: {exc}") from exc

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(storyboard), key=lambda e: list(e.path))
    if errors:
        formatted = [
            f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
            for err in errors[:10]
        ]
        raise StoryboardValidationError(
            "Storyboard failed JSON Schema validation:\n  - " + "\n  - ".join(formatted)
        )

    # Consent gate (PDF page 7: real person likeness or voice requires recorded consent)
    char = storyboard["character_sheet"]
    if char.get("is_real_person") and not char.get("consent_verified", False):
        raise StoryboardValidationError(
            "Consent gate blocked run: character_sheet.is_real_person is true, "
            "but character_sheet.consent_verified is false. Record consent in ETHICS.md first."
        )
    nar = storyboard["narration"]
    if nar.get("is_cloned_voice") and not nar.get("consent_verified", False):
        raise StoryboardValidationError(
            "Consent gate blocked run: narration.is_cloned_voice is true, "
            "but narration.consent_verified is false. Record consent in ETHICS.md first."
        )

    warnings: list[str] = []
    shots = storyboard["shots"]
    shot_ids = [s["id"] for s in shots]
    if len(set(shot_ids)) != len(shot_ids):
        raise StoryboardValidationError("Duplicate shot IDs found in storyboard.json.")

    total_shot_dur = sum(float(s["duration_sec"]) for s in shots)
    end_card_dur = (
        float(storyboard["end_card"]["duration_sec"])
        if storyboard["end_card"]["enabled"]
        else 0.0
    )
    total_duration = total_shot_dur + end_card_dur
    if not (55.0 <= total_duration <= 95.0):
        raise StoryboardValidationError(
            f"Total duration {total_duration:.1f}s is outside allowed 60-90s window (55-95s tolerance)."
        )
    if not (60.0 <= total_duration <= 90.0):
        warnings.append(f"Total film duration is {total_duration:.1f}s (target 60-90s).")

    music = storyboard["music"]
    if music["chosen_candidate_index"] >= music["candidates"]:
        raise StoryboardValidationError(
            f"music.chosen_candidate_index ({music['chosen_candidate_index']}) "
            f"must be < music.candidates ({music['candidates']})."
        )

    for shot in shots:
        lines = shot["subtitle_en"].splitlines()
        if len(lines) > 2:
            warnings.append(f"{shot['id']}: subtitle_en has {len(lines)} lines (recommended <= 2).")
        for line in lines:
            if len(line) > 42:
                warnings.append(
                    f"{shot['id']}: subtitle line exceeds 42 chars ({len(line)}): {line!r}"
                )

    return storyboard, warnings
