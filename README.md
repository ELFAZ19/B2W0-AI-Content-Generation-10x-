# Heritage Short AI Video Generation Pipeline

A reproducible, contract-driven studio pipeline that turns a validated [`storyboard.json`](storyboard.json) into a **60–90 second short film** exported in both **vertical (`9:16`, 1080×1920)** and **horizontal (`16:9`, 1920×1080)** formats—complete with localized narration, English subtitles inside safe areas, sidechain-ducked original score, `-14 LUFS` loudness normalization, and a visible AI disclosure end card.

---

## One-Command Run

From a clean clone (with Python 3.11+ and `ffmpeg`/`ffprobe` installed):

```bash
# 1. Create virtual environment and install dependencies
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure API keys (optional for offline/mock testing; required for live models)
cp .env.example .env

# 3. Run the entire pipeline end-to-end (one command)
python -m pipeline run --mode auto
```

Or using `Makefile` (Linux/macOS/WSL) or `run.ps1` (Windows PowerShell):

```bash
make film        # Final 9:16 + 16:9 export (or `.\run.ps1` on Windows)
make draft       # Fast 480p/540p draft export
make radio-cut   # Phase 1 checkpoint: narration + temp music on black screen
make rough-cut   # Phase 2 checkpoint: still keyframes + chosen score + narration
make smoke       # Smoke test configured providers and log latency to runs.jsonl
make test        # Run pytest suite
```

---

## What the Pipeline Does

Every stage reads **`storyboard.json`** (validated against [`schema/storyboard.schema.json`](schema/storyboard.schema.json) before running) and writes inspectable artifacts to `outputs/` plus structured call logs to `runs.jsonl`:

| Stage | Script | Model / Tool | Output |
|---|---|---|---|
| 1. Storyboard & Script | [`pipeline/script.py`](pipeline/script.py) | `gemini-3.8-flash` / `gemini-3.5-flash-lite` + JSON Schema | `outputs/script/storyboard_summary.json` |
| 2. Character Sheet & Keyframes | [`pipeline/keyframes.py`](pipeline/keyframes.py) | Cloudflare FLUX (`flux-2-klein-4b` / `flux-1-schnell`) or mock | `outputs/references/`, `outputs/keyframes/*.png` |
| 3. Line-by-Line Narration | [`pipeline/narration.py`](pipeline/narration.py) | `gemini-3.8-flash-tts` (130+ languages incl. Amharic) or mock | `outputs/narration/*.wav`, `subtitles.srt` |
| 4. Moving Shots | [`pipeline/shots.py`](pipeline/shots.py) | Wan 2.2 TI2V-5B (Kaggle worker) or FFmpeg Ken Burns fallback | `outputs/shots/*.mp4` |
| 5. Score Candidates | [`pipeline/music.py`](pipeline/music.py) | ACE-Step 1.5 (Kaggle/Colab worker) or FFmpeg ambient underscore | `outputs/music/candidate_*.wav`, `score_selected.wav` |
| 6. Mix, Subtitles & Export | [`pipeline/assemble.py`](pipeline/assemble.py) | FFmpeg (`sidechaincompress`, 2-pass `loudnorm -14 LUFS`, H.264/AAC) | `outputs/final/film_9x16.mp4`, `film_16x9.mp4` |

### Selective Regeneration (Input-Hash Caching)

Every item in every stage computes a deterministic SHA-256 hash of its inputs (character reference hash + `style_block` + shot prompt + seed + model). If you edit **one** shot's `keyframe_prompt` or `narration_line` in `storyboard.json` and re-run:

```bash
python -m pipeline run --mode auto
```

Only that changed shot regenerates (plus downstream assembly for the final MP4s), while all unchanged shots print `CACHE HIT` and make **zero** new model calls in `runs.jsonl`.

---

## Cost & Quota Summary

Designed for **\$0 out-of-pocket cost** on free tiers:
- **Gemini 3.8 Flash & TTS**: Google AI Studio free tier
- **Keyframes**: Cloudflare Workers AI daily free allowance (50–170 images/day)
- **Moving Shots & Score**: Kaggle 2× T4 (~30 GPU hrs/week) via `notebooks/` + built-in zero-cost FFmpeg Ken Burns & harmonic underscore fallbacks
- **Assembly**: Local CPU via FFmpeg (free, deterministic)

See [`COSTS.md`](COSTS.md) for measured stage timings and commercial list-price equivalents.
