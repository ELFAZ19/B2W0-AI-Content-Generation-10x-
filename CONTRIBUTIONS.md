# Project Implementation & Contributions

**Project:** Heritage Short AI Video Generation Pipeline (*The Brass Dial of Dessie*)  
**Repository:** [ELFAZ19/B2W0-AI-Content-Generation-10x-](https://github.com/ELFAZ19/B2W0-AI-Content-Generation-10x-)  
**Author / Contributor:** Elfaz Dejene ([@ELFAZ19](https://github.com/ELFAZ19))  
**Date:** November 2026  

---

## 1. Executive Summary of Contributions

This project designs and implements an end-to-end, contract-driven, multi-model AI video production pipeline. Starting from a validated single source of truth ([`storyboard.json`](storyboard.json)), the system autonomously generates a 78.5-second cinematic heritage short film with native Amharic narration, synchronized platform-safe subtitles, dynamic underscore music with audio ducking, broadcast-standard `-14 LUFS` loudness normalization, and dual-aspect export in both **vertical (`9:16`, 1080×1920)** and **horizontal (`16:9`, 1920×1080)** formats.

### Key Technical Contributions:
1. **Contract-Driven Architecture**: Standardized on JSON Schema Draft 2020-12 ([`schema/storyboard.schema.json`](schema/storyboard.schema.json)) with strict semantic validation and an ethical consent gate.
2. **Multi-Model Orchestration**: Integrated Google Gemini 3.8 Flash TTS, Cloudflare Workers AI FLUX models, Wan 2.2 TI2V-5B, and ACE-Step 1.5 into a unified execution graph.
3. **Deterministic Input-Hash Caching**: Engineered a SHA-256 asset caching engine that eliminates redundant API calls, allowing selective shot regeneration with zero wasted quota.
4. **Resilient Hybrid Fallback System**: Solved local consumer GPU hardware constraints (4 GB VRAM RTX 3050) by designing seamless fallbacks to remote GPU workers (Kaggle 2× T4) and deterministic FFmpeg motion graphics (Ken Burns) and harmonic audio synthesizers.
5. **Broadcast-Grade Audio & Video Engineering**: Implemented sidechain compression audio ducking, two-pass EBU R128 loudness normalization, aspect-aware safe margin subtitle burning, and an automated AI disclosure end card.
6. **Cross-Platform Tooling & Automated Verification**: Created automated CLI runners (`Makefile`, `run.ps1`), an automated code walkthrough generator, and an end-to-end `pytest` suite with 100% pass rate.

---

## 2. Detailed Implementation Breakdown

The codebase is structured under the [`pipeline/`](pipeline/) package, supported by schemas, tests, scripts, and notebooks:

```
project/
├── schema/
│   └── storyboard.schema.json       # Formal JSON Schema Draft 2020-12
├── pipeline/
│   ├── __init__.py                  # Package exports
│   ├── __main__.py                  # Entrypoint: python -m pipeline ...
│   ├── config.py                    # Environment & path configuration
│   ├── schema_validator.py          # Schema validation & consent gate
│   ├── script.py                    # Stage 1: Storyboard parser & validator
│   ├── keyframes.py                 # Stage 2: Character reference & FLUX images
│   ├── narration.py                 # Stage 3: Gemini Amharic TTS & SRT generator
│   ├── shots.py                     # Stage 4: Wan 2.2 Kaggle client & Ken Burns fallback
│   ├── music.py                     # Stage 5: ACE-Step 1.5 music & harmonic score
│   ├── assemble.py                  # Stage 6: Dual-aspect FFmpeg assembly & audio mix
│   ├── cache.py                     # Deterministic SHA-256 input-hash caching
│   ├── logger.py                    # Structured runs.jsonl logging & secret redaction
│   ├── retry.py                     # Exponential backoff with jitter
│   └── ffmpeg_utils.py              # FFmpeg wrapper with cross-platform path handling
├── scripts/
│   └── generate_walkthrough.py      # Automated video walkthrough generator
├── notebooks/
│   ├── kaggle_wan22_worker.py       # Kaggle worker for Wan 2.2 TI2V-5B
│   ├── kaggle_wan22_shots.py        # Kaggle batch inference script for shots
│   ├── kaggle_acestep_worker.py     # Kaggle worker for ACE-Step 1.5 music
│   └── kaggle_acestep_music.py      # Kaggle batch inference script for music
├── tests/
│   ├── test_schema_and_cache.py     # Schema, consent gate, and cache unit tests
│   └── test_pipeline_e2e.py         # End-to-end mock pipeline & retry test suite
├── storyboard.json                  # Source of truth story definition
├── run.ps1                          # Windows PowerShell orchestrator
├── Makefile                         # Unix / WSL build automation
├── ARCHITECTURE.md                  # System design & data flow documentation
├── COSTS.md                         # Detailed pricing & quota analysis
├── DESIGN.md                        # Audience analysis & user feedback log
├── ETHICS.md                        # Ethical disclosure & cultural authenticity
├── EXPERIMENTS.md                   # Systematic prompt & parameter experiments
├── FAILURES.md                      # Engineering failure journal & post-mortems
├── FINAL_REPORT.md                  # Comprehensive deliverable report
└── README.md                        # Project quickstart & overview
```

### Module Implementations & Responsibilities

#### 1. Ethical Governance & Contract Validation (`schema_validator.py`, `schema/`)
- Enforces strict compliance with `schema/storyboard.schema.json` before any pipeline code executes.
- **Ethical Consent Gate**: Validates that if `character_sheet.is_real_person` or `narration.is_cloned_voice` is `true`, an explicit `consent_verified: true` flag is present. If unverified, the pipeline refuses to execute, preventing non-consensual deepfakes or unauthorized voice cloning.
- Enforces duration boundaries (60–90 seconds), shot-by-shot artistic justifications (`reason`), camera movements, and mandatory AI disclosure.

#### 2. Visual Identity & Keyframe Synthesis (`keyframes.py`)
- Generates a primary character reference sheet (`ato_tesfaye_sheet.png`) and 9 distinct shot keyframes.
- Integrates Cloudflare Workers AI using `@cf/black-forest-labs/flux-2-klein-4b` with automatic fallback to `@cf/black-forest-labs/flux-1-schnell`.
- Implemented customized `multipart/form-data` payload handling for Klein 4B and parameter mapping for Schnell.
- Prepends character reference hash and consistent style blocks to maintain subject fidelity across all 9 scenes.

#### 3. Native Amharic Voiceover & Subtitles (`narration.py`)
- Synthesizes per-shot Amharic narration using Google Gemini 3.8 Flash TTS (`gemini-3.8-flash-tts`, `Charon` voice) via the official `google-genai` SDK.
- Pre-normalizes individual audio stems to `-18.0 LUFS`.
- Dynamically aligns audio duration with shot duration using silence padding to prevent abrupt cuts, while avoiding voice distortion.
- Generates synchronized SubRip (`.srt`) subtitles with platform-safe wrapping constraints (`<= 2 lines` per cue, `<= 40 characters` per line).

#### 4. Video Motion & Dynamic Shots (`shots.py`)
- Provides a dual execution path:
  - **Live Worker Mode**: Dispatches image-to-video inference requests to remote Kaggle GPU workers running Wan 2.2 TI2V-5B.
  - **Deterministic Motion Fallback**: Implements high-quality 24fps FFmpeg Ken Burns motion graphics (`zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `static`) matching the storyboard's `camera_movement` directives.
- Guarantees 100% pipeline completion even in environments without local or remote GPU resources.

#### 5. Original Underscore Generation (`music.py`)
- Orchestrates score candidate generation with ACE-Step 1.5 across multiple deterministic seeds (4200, 4201, 4202).
- Includes a standalone FFmpeg harmonic synthesizer fallback creating layered acoustic underscore matched to story progression.
- Automatically normalizes the selected score to `-22.0 LUFS` prior to final assembly.

#### 6. Dual-Aspect Assembly & Master Mix (`assemble.py`, `ffmpeg_utils.py`)
- **Video Rendering**: Simultaneously renders vertical (`9:16`, `1080x1920`) for mobile platforms and horizontal (`16:9`, `1920x1080`) for widescreen playback at constant 24 fps H.264.
- **Audio Ducking**: Utilizes FFmpeg `sidechaincompress` to duck the musical score by 6 dB whenever narration is active, restoring volume during silent beats.
- **Broadcast Loudness**: Implements two-pass EBU R128 loudness normalization targeting `-14.0 LUFS` integrated loudness and `-1.0 dBTP` maximum true peak.
- **Safe-Area Subtitles**: Dynamically adjusts vertical subtitle positioning (`MarginV=14%` on 9:16 to clear mobile app UI overlays; `MarginV=6%` on 16:9).
- **AI Disclosure**: Renders and appends a standardized 2.5-second `"Made with AI"` end card with project attribution.

#### 7. Performance & Reliability Infrastructure (`cache.py`, `logger.py`, `retry.py`)
- **Deterministic Caching**: Tracks SHA-256 digests of all prompts, model configs, seeds, and upstream dependencies in `outputs/.cache_manifest.json`. Unchanged items are served from cache with 0 ms latency and 0 API cost.
- **Audit Logging**: Every stage call writes a structured record to `runs.jsonl` tracking latency, token usage, estimated costs, and seeds, with automated masking of API keys and bearer tokens.
- **Resilient Retries**: Implements exponential backoff with jitter for transient 429 rate limits and 5xx errors, while instantly failing on non-retryable authentication or schema errors.

---

## 3. Engineering Challenges Solved

| Challenge | Root Cause | Solution Implemented |
|---|---|---|
| **GPU VRAM Limitations** | Local workstation GPU (RTX 3050 Laptop) has only 4 GB VRAM, insufficient for Wan 2.2 5B. | Developed Kaggle GPU worker scripts (`notebooks/`) and built an automatic FFmpeg Ken Burns motion fallback to ensure complete offline/local testability. |
| **Cloudflare FLUX API Differences** | `flux-2-klein-4b` requires `multipart/form-data`, while `flux-1-schnell` requires JSON with specific step parameters. | Implemented custom payload routing and automatic model fallback in `pipeline/keyframes.py`. |
| **Windows FFmpeg Filter Parsing** | FFmpeg filtergraphs interpret drive letter colons (`C:\...`) as option separators, breaking subtitle burn-in. | Isolated subtitle processing to relative filenames within temporary working directories (`cwd=work_dir`). |
| **Amharic TTS Timing Clipping** | Initial shot durations were shorter than natural Amharic spoken cadence. | Analyzed exact audio stem lengths, updated `storyboard.json` to 76.0s (78.5s with end card), and applied automated silence padding. |
| **Zero-Cost Constraint** | Production-quality generative pipelines often require paid API credits. | Architected the pipeline exclusively on free tiers (Google AI Studio, Cloudflare Workers AI free tier, Kaggle T4 GPUs, local FFmpeg) achieving **$0.00** total expenditure. |

---

## 4. Verification and Quality Assurance

- **Unit & Integration Tests**: Executed `pytest -v` with 9 comprehensive tests covering:
  - Full mock end-to-end pipeline execution (`test_full_pipeline_mock_end_to_end`).
  - Strict schema validation against `schema/storyboard.schema.json` (`test_default_storyboard_validates`).
  - Ethical consent gate blocking unverified real-person claims (`test_consent_gate_blocks_unverified_real_person`).
  - Mandatory shot reason validation (`test_schema_rejects_missing_shot_reason`).
  - Selective single-shot cache invalidation (`test_cache_manifest_invalidates_only_changed_item`, `test_single_shot_edit_regenerates_only_one_shot`).
  - Exponential backoff retry logic (`test_retry_exponential_and_non_retryable`).
  - Secret redaction in audit logs (`test_run_logger_redacts_secrets`).
  - Safe-area subtitle character and line length constraints (`test_subtitle_wrapping_constraints`).
- **Media Verification**: Verified output streams with `ffprobe` for frame rates (24.0 fps), audio sample rates (48 kHz), loudness (`-14 LUFS`), and bitrates.

---

## 5. Summary of Project Deliverables

- **Final Film Exports**:
  - `outputs/final/film_16x9.mp4` (1920×1080 horizontal, 78.5s)
  - `outputs/final/film_9x16.mp4` (1080×1920 vertical, 78.5s)
- **Phase 1 Checkpoint**: `outputs/radio_cut/radio_cut_16x9.mp4` (narration + temp score)
- **Video Walkthrough**: `outputs/walkthrough/python_walkthrough_16x9.mp4`
- **Audit Logs**: `runs.jsonl` (90+ tracked operations with timing and provider metrics)
- **Documentation**:
  - [`README.md`](README.md): Quickstart and pipeline guide
  - [`CONTRIBUTIONS.md`](CONTRIBUTIONS.md): Implementation breakdown and engineering contributions
  - [`ARCHITECTURE.md`](ARCHITECTURE.md): System architecture and data flow
  - [`FINAL_REPORT.md`](FINAL_REPORT.md): Executive summary and measured run metrics
  - [`COSTS.md`](COSTS.md): Cost breakdown and quota analysis
  - [`ETHICS.md`](ETHICS.md): Ethical compliance, consent gate, and cultural authenticity
  - [`DESIGN.md`](DESIGN.md): Audience research and shot justifications
  - [`EXPERIMENTS.md`](EXPERIMENTS.md): Systematic experiment logs
  - [`FAILURES.md`](FAILURES.md): Failure post-mortems and resolutions
