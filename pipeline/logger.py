"""Structured JSONL logging to runs.jsonl for every model and stage call."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.config import LIST_PRICE_EQUIVALENTS


_SECRET_SUBSTRINGS = ("key", "token", "secret", "password", "authorization")


def _sanitize(obj: Any) -> Any:
    """Strip any accidental secret-looking keys before persisting logs."""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            if any(tok in str(k).lower() for tok in _SECRET_SUBSTRINGS):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = _sanitize(v)
        return cleaned
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    return obj


class RunLogger:
    """Append-only JSONL logger writing one structured record per model/stage call."""

    def __init__(self, log_path: Path, run_id: str | None = None) -> None:
        self.log_path = log_path
        self.run_id = run_id or uuid.uuid4().hex[:12]

    def log_call(
        self,
        *,
        stage: str,
        shot_id: str | None,
        provider: str,
        model: str,
        parameters: dict[str, Any],
        seed: int | None,
        latency_s: float,
        gpu_minutes: float = 0.0,
        cost_usd: float | None = None,
        cache_hit: bool = False,
        input_hash: str = "",
        status: str = "ok",
        error: str | None = None,
        outputs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Append one call record to runs.jsonl and return it."""
        if cost_usd is None:
            cost_usd = 0.0 if cache_hit else LIST_PRICE_EQUIVALENTS.get(model, 0.0)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "stage": stage,
            "shot_id": shot_id,
            "provider": provider,
            "model": model,
            "parameters": _sanitize(parameters),
            "seed": seed,
            "latency_s": round(float(latency_s), 4),
            "gpu_minutes": round(float(gpu_minutes), 4),
            "cost_usd": round(float(cost_usd), 6),
            "cache_hit": bool(cache_hit),
            "input_hash": input_hash,
            "status": status,
            "error": error,
            "outputs": outputs or [],
        }

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
