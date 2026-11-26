# Final Report — Heritage Short AI Video Generation Pipeline

**Project Title:** *The Brass Dial of Dessie* (Amharic-narrated 76s short + 2.5s AI disclosure end card)  
**Target Directory:** `C:\2017\2017\2017\vs code\10x\B2W0 AI Content Generatio\project`  
**Total Paid API Cost:** **\$0.00** (Free-tier APIs + local FFmpeg)

---

## 1. Executive Summary & Deliverables

The end-to-end AI video generation pipeline has been implemented, validated, tested, and executed with live AI providers to produce both vertical (`9:16`) and horizontal (`16:9`) final exports.

| Deliverable | Path | Verified Specs |
|---|---|---|
| **16:9 Final Film** | `outputs/final/film_16x9.mp4` | `1920×1080`, H.264 + AAC 48 kHz, `78.5s`, `19.69 MB` |
| **9:16 Final Film** | `outputs/final/film_9x16.mp4` | `1080×1920`, H.264 + AAC 48 kHz, `78.5s`, `19.24 MB` |
| **Phase 1 Radio Cut** | `outputs/radio_cut/radio_cut_16x9.mp4` | `1280×720`, H.264 + AAC 48 kHz, `68.0s`, `1.88 MB` |
| **Python Walkthrough Video** | `outputs/walkthrough/python_walkthrough_16x9.mp4` | `1920×1080`, H.264 + AAC 48 kHz, narrated code walkthrough |
| **Final Report** | `FINAL_REPORT.md` | This document |

---

## 2. Pipeline Architecture

The pipeline is driven by a single source-of-truth contract ([storyboard.json](storyboard.json)) validated against [schema/storyboard.schema.json](schema/storyboard.schema.json) (JSON Schema Draft 2020-12):

1. **Stage 1 — Script & Validation (`pipeline/script.py`, `pipeline/schema_validator.py`)**: Enforces schema compliance, 60–90s target duration, `ai_disclosure: true`, and the real-person/voice-cloning consent gate.
2. **Stage 2 — Character Reference & Keyframes (`pipeline/keyframes.py`)**: Generates a character reference sheet (`ato_tesfaye_sheet.png`) and 9 shot keyframes (`shot_01.png`–`shot_09.png`) using Cloudflare Workers AI (`@cf/black-forest-labs/flux-2-klein-4b`, with `@cf/black-forest-labs/flux-1-schnell` fallback).
3. **Stage 3 — Amharic Narration & SRT (`pipeline/narration.py`)**: Synthesizes per-shot Amharic voiceover using Gemini 3.8 Flash TTS (`gemini-3.8-flash-tts`, `Charon` voice) via the `google-genai` Interactions API (`v1beta`), normalizes each stem to `-18 LUFS`, aligns to shot duration, and generates `subtitles.srt`.
4. **Stage 4 — Moving Shots (`pipeline/shots.py`)**: Imports Wan 2.2 TI2V-5B clips from `outputs/kaggle_shots/` when present, or falls back deterministically to FFmpeg Ken Burns motion (`zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `static`) at `1280×720` / 24 fps.
5. **Stage 5 — Underscore Music (`pipeline/music.py`)**: Imports ACE-Step 1.5 candidates from `outputs/kaggle_music/` when present, or generates 3 seeded FFmpeg acoustic-style underscore candidates (`base_seed` 4200–4202).
6. **Stage 6 — Dual-Aspect Assembly (`pipeline/assemble.py`, `pipeline/ffmpeg_utils.py`)**:
   - Mixes narration + music with `sidechaincompress` ducking.
   - Applies two-pass EBU R128 loudness normalization (`-14 LUFS`, `-1.0 dBTP`).
   - Burns English subtitles with safe aspect-aware margins (`14%` bottom margin on `9:16`, `6%` on `16:9`).
   - Appends a `2.5s` `"Made with AI"` disclosure end card.

---

## 3. Observed Live Run Metrics (from `runs.jsonl`)

| Stage | Provider | Model | Items | Avg Latency | Total Time |
|---|---|---|---:|---:|---:|
| `keyframes_ref` | `cloudflare` | `@cf/black-forest-labs/flux-2-klein-4b` | 1 | 11.08s | 11.08s |
| `keyframes` | `cloudflare` | `@cf/black-forest-labs/flux-2-klein-4b` | 9 | 13.37s | 120.30s |
| `narration` | `gemini` | `gemini-3.8-flash-tts` | 9 | 13.39s | 120.50s |
| `shots` | `ffmpeg-fallback` | `ffmpeg-ken-burns` | 9 | 2.04s | 18.38s |
| `music` | `ffmpeg-fallback` | `ffmpeg-synth-audio` | 3 | 5.64s | 16.91s |
| `script` | `local` | `jsonschema-validator` | 1 | 0.01s | 0.01s |

---

## 4. Issues Encountered & Resolutions

1. **Schema validation mismatch (`consent_recorded`)**: `storyboard.json` contained an extra `consent_recorded` key rejected by `additionalProperties: false`. Removed it; `validate` passed with `0 warnings`.
2. **Cloudflare TLS reset (`WinError 10054`)**: Direct connections to `api.cloudflare.com` were reset at the network level; resolved by routing over VPN.
3. **Cloudflare FLUX payload format (`400 Bad Request`)**:
   - `@cf/black-forest-labs/flux-2-klein-4b` requires `multipart/form-data` (`files=...`) instead of JSON.
   - `@cf/black-forest-labs/flux-1-schnell` expects `{"prompt": ..., "steps": 4}` rather than `num_steps`/`seed`/`width`/`height`.
   - Updated `pipeline/keyframes.py` and `pipeline/smoke_test.py` accordingly; all 10 Cloudflare images then succeeded on `flux-2-klein-4b`.
4. **Narration clipping on 5 shots**: Initial `7.0s`–`7.5s` shot durations trimmed the end of Amharic TTS lines (which ran `8.18s`–`9.68s`). Extended those shot durations in `storyboard.json` (total `76.0s` + `2.5s` end card = `78.5s`) and re-ran assembly with zero TTS cache misses.
5. **Windows FFmpeg subtitle filter path**: Absolute Windows paths with drive letters break FFmpeg's `subtitles=` filtergraph; resolved by copying `subs.srt` into the temp working directory and running FFmpeg with `cwd=work_dir`.

---

## 5. Automated Verification

Executed `pytest -v` after updating `storyboard.json`:
- **9/9 tests passed** in `80.79s`:
  - `test_full_pipeline_mock_end_to_end`
  - `test_default_storyboard_validates`
  - `test_consent_gate_blocks_unverified_real_person`
  - `test_schema_rejects_missing_shot_reason`
  - `test_cache_manifest_invalidates_only_changed_item`
  - `test_retry_exponential_and_non_retryable`
  - `test_run_logger_redacts_secrets`
  - `test_subtitle_wrapping_constraints`
  - `test_single_shot_edit_regenerates_only_one_shot`
