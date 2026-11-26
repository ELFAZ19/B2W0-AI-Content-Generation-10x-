# Experiment Log (`EXPERIMENTS.md`)

Format: **Hypothesis -> Change -> Result (with evidence from `runs.jsonl` / outputs)**.
Target at least 10 logged experiments across narration prosody, character consistency, Wan 2.2 motion prompts, ACE-Step score candidates, and FFmpeg ducking/subtitles as you run live generations.

---

### EXP-001: Deterministic Input-Hash Caching on Single-Shot Edit
- **Hypothesis**: Hashing each shot's upstream inputs (`approved_ref_sha`, `style_block`, `keyframe_prompt`, `seed`) will regenerate only the edited shot on re-run without triggering API calls for unchanged shots.
- **Change**: Edited `shot_03.keyframe_prompt` in an isolated test copy of `storyboard.json` and re-ran the full pipeline (`tests/test_cache.py` & `tests/test_pipeline_e2e.py`).
- **Result**: Only `shot_03` regenerated in `keyframes`, `shots`, and `assemble`; the remaining 8 shots hit cache (`CACHE HIT`) with 0 new model calls logged for them in `runs.jsonl`.

### EXP-002: Safe-Area Subtitle Margin on Vertical (`9:16`) Exports
- **Hypothesis**: Standard bottom subtitle margins (`6%`) get covered by TikTok/Reels/Shorts UI buttons on `1080x1920`, whereas a `14%` `MarginV` with <= 2 lines / <= 40 chars keeps captions readable.
- **Change**: Configured `assemble.py` to wrap SRT lines at 40 chars (`wrap_subtitle_text`) and apply `MarginV = int(height * 0.14)` for `9:16` vs `int(height * 0.06)` for `16:9`.
- **Result**: Verified SRT line bounds in unit tests and visual placement in `outputs/final/film_9x16.mp4`.

---

### Ready-to-Log Live Model Experiments (EXP-003 .. EXP-010)
*Fill these as you run live Gemini TTS, Cloudflare FLUX, Wan 2.2, and ACE-Step 1.5 generations:*

| ID | Stage | Hypothesis | Change (One Variable, Fixed Seed) | Measured Result (`runs.jsonl` / Listener Check) | Keep? |
|---|---|---|---|---|---|
| EXP-003 | Narration | Calm elder style annotation improves Amharic pacing | `style_instruction` tuned on `shot_01` | | |
| EXP-004 | Narration | Shorter Amharic clauses avoid rushed TTS delivery | Split long sentence in `shot_05` | | |
| EXP-005 | Keyframes | Prepending `character_sheet` + `style_block` locks identity | Generate 4 options for ref sheet, pick best seed | | |
| EXP-006 | Keyframes | `flux-2-klein-4b` vs `flux-1-schnell` facial fidelity | Same prompt & seed across both models | | |
| EXP-007 | Shots | Motion-only I2V prompt reduces morphing vs re-describing subject | Drop subject nouns from `motion_prompt` | | |
| EXP-008 | Shots | 480p draft vs 720p final Wan 2.2 GPU minutes | Compare `runs_kaggle.jsonl` latency | | |
| EXP-009 | Music | Audition 3 ACE-Step seeds (`4200..4202`), pick least busy midrange | Blind listen under Amharic voice | | |
| EXP-010 | Mix | Tune `sidechaincompress` threshold (`0.02` vs `0.03`) | Compare speech clarity on phone speaker | | |
