# Pipeline Architecture

## Design Principle: One Contract (`storyboard.json`)

All six stages communicate exclusively through `storyboard.json`, which is validated against `schema/storyboard.schema.json` before any generation runs. No prompts, seeds, durations, or voice selections are hardcoded inside Python scripts.

```text
  [story brief]
        │
        ▼
  1. pipeline/script.py  ──(validates schema & consent gate)──► storyboard.json
        │
        ├──► 2. pipeline/keyframes.py  ──► outputs/references/ + outputs/keyframes/*.png
        │          │
        │          ▼
        │    3. pipeline/shots.py      ──► outputs/shots/*.mp4 (Wan 2.2 or Ken Burns)
        │
        ├──► 4. pipeline/narration.py  ──► outputs/narration/*.wav + subtitles.srt
        │
        └──► 5. pipeline/music.py      ──► outputs/music/candidate_*.wav + score_selected.wav
                   │
                   ▼
             6. pipeline/assemble.py   ──► outputs/final/film_9x16.mp4 + film_16x9.mp4
```

## Caching Strategy (`pipeline/cache.py`)

Outputs are tracked in `outputs/.cache_manifest.json` keyed by `stage:item_id`.
- **Keyframes** hash: `approved_ref_sha + style_block + character_description + keyframe_prompt + shot_size + seed + provider + model`.
- **Narration** hash: `narration_line + model + voice + style_instruction + language_code + provider`.
- **Shots** hash: `keyframe_sha256 + kaggle_sha256 + motion_prompt + camera_movement + fallback_motion + duration_sec + trim_start_sec + seed + quality + model`.
- **Music** hash: `candidate_index + seed + caption + lyrics + tempo_bpm + key + duration_sec + model`.
- **Assembly** hash: `cut_type + quality + narration_sha256 + music_sha256 + srt_sha256 + end_card + shot clip sha256s`.

A cache entry is valid only if **both** the SHA-256 input digest matches **and** every expected output file exists and is non-empty. Cache hits skip model calls completely and do not append duplicate billable call entries to `runs.jsonl`.

## Failure Handling & Retries (`pipeline/retry.py`)

1. **Transient HTTP/API errors** (429 rate limits, 5xx, timeouts): retried up to 3 times with jittered exponential backoff (`base=1.5s`, `max=15s`).
2. **Non-retryable errors** (`NonRetryableError` for 401/403 bad keys or failed schema/consent validation): fail fast without wasting quota.
3. **Model & GPU fallback**:
   - If Cloudflare `flux-2-klein-4b` fails, `keyframes.py` automatically falls back to `flux-1-schnell`.
   - If `WAN_WORKER_URL` is unreachable or unconfigured in `auto` mode, `shots.py` logs the failure and falls back to deterministic 24fps FFmpeg Ken Burns motion (`zoompan`) driven by each shot's `camera_movement`.
4. **Ethical Consent Gate (`pipeline/schema_validator.py`)**: Before any generation runs, if `character_sheet.is_real_person` or `narration.is_cloned_voice` is `true` without `consent_verified: true`, validation aborts immediately.

## Audio Mixing & Dual-Aspect Export (`pipeline/assemble.py`)

1. Per-shot narration WAVs are pre-normalized (`-18 LUFS`) and padded/trimmed to exact shot durations before concatenation.
2. Score is normalized (`-22 LUFS`) and ducked underneath narration using FFmpeg `sidechaincompress` (`threshold=0.02:ratio=6:attack=300:release=1500`).
3. Two-pass FFmpeg `loudnorm` targets `-14.0 LUFS` integrated loudness and `-1.0 dBTP` true peak.
4. Video clips are center-cropped/scaled cleanly to `1080x1920` (9:16) and `1920x1080` (16:9) at constant `24 fps`. Subtitles are wrapped (`<= 2 lines`, `<= 40 chars/line`) and positioned inside platform safe margins (`14%` bottom margin on 9:16, `6%` on 16:9), followed by a 2.5s `Made with AI` end card.
