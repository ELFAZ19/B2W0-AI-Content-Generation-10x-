"""Configuration, paths, model identifiers, and pricing metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


# Default models matching the PDF specification ("The Stack, at Zero Cost")
DEFAULT_GEMINI_TEXT_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_LITE_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"
DEFAULT_CF_IMAGE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
DEFAULT_CF_FALLBACK_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
DEFAULT_VIDEO_MODEL = "Wan-AI/Wan2.2-TI2V-5B"
DEFAULT_MUSIC_MODEL = "ACE-Step/ACE-Step-1.5"

# Reference list-price equivalents (USD) used for COSTS.md accounting
LIST_PRICE_EQUIVALENTS = {
    DEFAULT_GEMINI_TEXT_MODEL: 0.0005,
    DEFAULT_GEMINI_LITE_MODEL: 0.0001,
    DEFAULT_GEMINI_TTS_MODEL: 0.0020,
    DEFAULT_CF_IMAGE_MODEL: 0.0150,
    DEFAULT_CF_FALLBACK_IMAGE_MODEL: 0.0030,
    DEFAULT_VIDEO_MODEL: 0.2500,
    DEFAULT_MUSIC_MODEL: 0.0500,
    "ffmpeg-ken-burns": 0.0,
    "ffmpeg-assemble": 0.0,
    "ffmpeg-synth-audio": 0.0,
    "mock-tts": 0.0,
    "mock": 0.0,
}


@dataclass(frozen=True)
class PipelineConfig:
    """Resolved runtime configuration and stage directories for a pipeline invocation."""

    root: Path
    storyboard_path: Path
    schema_path: Path
    outputs_dir: Path
    runs_log_path: Path
    cache_manifest_path: Path
    mode: str  # "auto" | "live" | "mock"
    gemini_api_key: str | None
    cloudflare_account_id: str | None
    cloudflare_api_token: str | None
    cloudflare_image_model: str
    hf_token: str | None
    wan_worker_url: str | None
    wan_worker_token: str | None
    acestep_worker_url: str | None
    acestep_worker_token: str | None

    @property
    def references_dir(self) -> Path:
        return self.outputs_dir / "references"

    @property
    def keyframes_dir(self) -> Path:
        return self.outputs_dir / "keyframes"

    @property
    def shots_dir(self) -> Path:
        return self.outputs_dir / "shots"

    @property
    def music_dir(self) -> Path:
        return self.outputs_dir / "music"

    @property
    def narration_dir(self) -> Path:
        return self.outputs_dir / "narration"

    @property
    def radio_cut_dir(self) -> Path:
        return self.outputs_dir / "radio_cut"

    @property
    def rough_cut_dir(self) -> Path:
        return self.outputs_dir / "rough_cut"

    @property
    def final_dir(self) -> Path:
        return self.outputs_dir / "final"

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_cloudflare(self) -> bool:
        return bool(self.cloudflare_account_id and self.cloudflare_api_token)

    @property
    def has_wan_worker(self) -> bool:
        return bool(self.wan_worker_url)

    @property
    def has_acestep_worker(self) -> bool:
        return bool(self.acestep_worker_url)

    def ensure_dirs(self) -> None:
        for d in (
            self.outputs_dir,
            self.references_dir,
            self.keyframes_dir,
            self.shots_dir,
            self.music_dir,
            self.narration_dir,
            self.radio_cut_dir,
            self.rough_cut_dir,
            self.final_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_provider(self, available: bool, provider_name: str) -> str:
        """Return 'live' or 'mock' according to mode and credential availability."""
        if self.mode == "mock":
            return "mock"
        if self.mode == "live":
            if not available:
                raise RuntimeError(
                    f"PIPELINE_PROVIDER_MODE=live requires credentials for {provider_name}. "
                    "Set them in .env or switch PIPELINE_MODE=auto/mock."
                )
            return "live"
        return "live" if available else "mock"


def load_config(
    root: Path | None = None,
    mode: str | None = None,
    storyboard_path: Path | None = None,
) -> PipelineConfig:
    """Load runtime configuration from environment and optional overrides."""
    base = (root or PROJECT_ROOT).resolve()
    load_dotenv(base / ".env", override=False)

    resolved_mode = (
        mode
        or os.getenv("PIPELINE_PROVIDER_MODE")
        or os.getenv("PIPELINE_MODE", "auto")
    ).strip().lower()
    if resolved_mode not in {"auto", "live", "mock"}:
        raise ValueError(f"Unsupported PIPELINE_MODE={resolved_mode!r}; expected auto, live, or mock.")

    outputs_dir = base / "outputs"
    return PipelineConfig(
        root=base,
        storyboard_path=(storyboard_path or (base / "storyboard.json")).resolve(),
        schema_path=(base / "schema" / "storyboard.schema.json").resolve(),
        outputs_dir=outputs_dir,
        runs_log_path=base / "runs.jsonl",
        cache_manifest_path=outputs_dir / ".cache_manifest.json",
        mode=resolved_mode,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID") or None,
        cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN") or None,
        cloudflare_image_model=os.getenv("CLOUDFLARE_IMAGE_MODEL", DEFAULT_CF_IMAGE_MODEL),
        hf_token=os.getenv("HF_TOKEN") or None,
        wan_worker_url=(os.getenv("WAN_WORKER_URL") or os.getenv("WAN_SPACE_URL") or None),
        wan_worker_token=os.getenv("WAN_WORKER_TOKEN") or None,
        acestep_worker_url=(os.getenv("ACESTEP_WORKER_URL") or os.getenv("ACESTEP_SPACE_URL") or None),
        acestep_worker_token=os.getenv("ACESTEP_WORKER_TOKEN") or None,
    )
