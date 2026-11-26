# Failure Journal (`FAILURES.md`)

Honest record of blockers encountered, diagnostic steps, and resolutions or workarounds.

---

### FAIL-001: Local GPU VRAM Insufficient for Wan 2.2 TI2V-5B (4 GB RTX 3050)
- **Symptom / Blocker**: Local workstation GPU (`NVIDIA GeForce RTX 3050 Laptop GPU`) has `4096 MiB` (4 GB) VRAM, which cannot fit Wan 2.2 TI2V-5B weights in `bf16` without severe CPU offloading timeouts or OOM.
- **What Was Tried**: Checked `nvidia-smi` during environment inspection; kept local machine dedicated to orchestration, Gemini/Cloudflare API calls, and deterministic FFmpeg assembly.
- **Resolution / Workaround**: Created `notebooks/kaggle_wan22_worker.py` (for Kaggle `2× T4`, drafting at `832x480` first) with automatic ingestion from `outputs/kaggle_shots/`, and built a deterministic 24fps FFmpeg Ken Burns fallback (`render_still_or_ken_burns_clip`) in `pipeline/shots.py` so the pipeline always completes end-to-end.

### FAIL-002: `make` Not Installed on Windows PowerShell Host
- **Symptom / Blocker**: Running `make --version` failed (`CommandNotFoundException`) on Windows 11.
- **What Was Tried**: Checked local toolchain (`python 3.13`, `ffmpeg 8.1.1`, `git`, `node` present; `make` absent).
- **Resolution / Workaround**: Provided both `Makefile` (for Linux/macOS/WSL/Git Bash) and cross-platform `python -m pipeline run` + `run.ps1` so one-command execution works on every OS.

### FAIL-003: FFmpeg `subtitles` Filter Path Parsing on Windows Drive Letters
- **Symptom / Blocker**: On Windows, passing an absolute path like `C:\...\subtitles.srt` directly into FFmpeg `-vf subtitles=...` fails because FFmpeg's filtergraph parser treats `:` after `C` as an option separator.
- **What Was Tried**: Escaping backslashes vs changing working directory.
- **Resolution / Workaround**: `pipeline/assemble.py` copies the SRT to `subs.srt` inside the stage's temporary `work_dir` and runs `ffmpeg` with `cwd=work_dir` using relative filenames (`subtitles=subs.srt:...`), making subtitle burn-in 100% OS-independent.

---

### Live Provider Blockers Log (Add real quota, language, or consistency issues here)
- *(Log any Gemini TTS Amharic/Afaan Oromo pronunciation glitches, Cloudflare rate-limit 429s, or Kaggle GPU queue/OOM failures as you run live models.)*
