# Cost, Latency & Quota Accounting (`COSTS.md`)

## 1. Zero-Cost Stack & Free Tier Allowances

| Stage | Model / Tool | Provider / Host | Free Tier / Quota Notes |
|---|---|---|---|
| Script & Translation | `gemini-3.8-flash`, `gemini-3.5-flash-lite` | Google AI Studio (Gemini API) | Free tier supported (verify RPM/RPD limits at start of run) |
| Narration (TTS) | `gemini-3.8-flash-tts` | Google AI Studio (Gemini API) | Free tier; 130+ languages incl. Amharic, Tigrinya, Somali |
| Keyframes | `FLUX.2 klein 4B` / `FLUX.1 schnell` | Cloudflare Workers AI | Daily free neuron allowance (~50–170 images/day) |
| Moving Shots | `Wan 2.2 TI2V-5B` / FFmpeg Ken Burns | Kaggle (`2× T4`, ~30 GPU hrs/week) or Local CPU | Draft at 480p before 720p; local Ken Burns is \$0 & ~1–2s/shot |
| Music / Score | `ACE-Step 1.5` / FFmpeg underscore | Kaggle / Colab (<4 GB VRAM) or Local CPU | MIT-licensed weights; outputs commercially usable |
| Assembly | `FFmpeg` + `Pillow` | Local machine | \$0, deterministic |

---

## 2. Measured Latency, GPU Minutes & Commercial List-Price Equivalent

Every live or mock model call automatically appends `latency_s`, `gpu_minutes`, and `cost_usd` (commercial list-price equivalent from `pipeline/config.py`) into `runs.jsonl`.

Run a quick summary from `runs.jsonl` anytime with:

```bash
python -c "import json, collections; rows=[json.loads(l) for l in open('runs.jsonl')]; by_s=collections.defaultdict(lambda:[0,0.0,0.0,0.0]); [by_s[r['stage']].__setitem__(0, by_s[r['stage']][0]+1) or by_s[r['stage']].__setitem__(1, by_s[r['stage']][1]+r['latency_s']) or by_s[r['stage']].__setitem__(2, by_s[r['stage']][2]+r['gpu_minutes']) or by_s[r['stage']].__setitem__(3, by_s[r['stage']][3]+r['cost_usd']) for r in rows]; print('\n'.join(f'{k}: calls={v[0]} latency={v[1]:.2f}s gpu_min={v[2]:.3f} equiv=\${v[3]:.4f}' for k,v in by_s.items()))"
```

### Reference List-Price Equivalents Configured (`pipeline/config.py`)
- `gemini-3.8-flash`: \$0.0005 / call
- `gemini-3.5-flash-lite`: \$0.0001 / call
- `gemini-3.8-flash-tts`: \$0.0020 / line
- `@cf/black-forest-labs/flux-2-klein-4b`: \$0.0150 / image
- `@cf/black-forest-labs/flux-1-schnell`: \$0.0030 / image
- `Wan-AI/Wan2.2-TI2V-5B`: \$0.2500 / clip equivalent
- `ACE-Step/ACE-Step-1.5`: \$0.0500 / candidate track equivalent
- Local `ffmpeg-ken-burns`, `ffmpeg-synth-audio`, `ffmpeg-assemble`: \$0.0000

*(Update this table with your measured Kaggle GPU minutes and frontier comparison numbers after completing Phase 2 & 3 live runs.)*
