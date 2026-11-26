"""Content-addressed caching so re-runs only regenerate changed items."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def compute_input_hash(payload: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 digest of a JSON-serializable input payload."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str | None:
    """Return SHA-256 hex digest of a file, or None if it does not exist."""
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CacheManifest:
    """Persistent JSON cache tracking stage/item input hashes and output paths."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, dict):
                    self._data = raw
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.manifest_path.with_suffix(".tmp.json")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        tmp_path.replace(self.manifest_path)

    @staticmethod
    def _key(stage: str, item_id: str) -> str:
        return f"{stage}:{item_id}"

    def is_valid(
        self,
        stage: str,
        item_id: str,
        input_hash: str,
        expected_outputs: list[Path],
        force: bool = False,
    ) -> bool:
        """Return True iff cached input_hash matches and all output files exist."""
        if force:
            return False
        entry = self._data.get(self._key(stage, item_id))
        if not entry or entry.get("input_hash") != input_hash:
            return False
        return all(p.exists() and p.stat().st_size > 0 for p in expected_outputs)

    def get(self, stage: str, item_id: str) -> dict[str, Any] | None:
        return self._data.get(self._key(stage, item_id))

    def record(
        self,
        stage: str,
        item_id: str,
        input_hash: str,
        outputs: list[Path],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._data[self._key(stage, item_id)] = {
            "input_hash": input_hash,
            "outputs": [str(p) for p in outputs],
            "metadata": metadata or {},
        }
        self.save()
