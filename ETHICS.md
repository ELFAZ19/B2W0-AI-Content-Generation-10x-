# Ethics, Consent, Licences & Labelling (`ETHICS.md`)

## 1. Consent Record (Real Person Likeness & Voice Gate)

> **Hard Gate Enforced in Code (`pipeline/schema_validator.py`)**:
> If `character_sheet.is_real_person` or `narration.is_cloned_voice` is `true`, the pipeline refuses to run unless `consent_verified` is explicitly `true` and documented here.

- **Current Storyboard Subject (`storyboard.json`)**: `Ato Tesfaye (fictional composite craftsman)`
  - `character_sheet.is_real_person`: `false`
  - `narration.is_cloned_voice`: `false` (uses standard Gemini prebuilt voice `Charon`)
  - **Status**: No real person's face, likeness, or cloned voice is used in the default template storyboard.

### Template for Real Family / Subject Consent (Fill before changing `is_real_person: true`)
| Subject Name | Role in Film | Likeness / Voice Used | Informed Consent Date & Medium | Agreed Script / Lines Approved? | Notes |
|---|---|---|---|---|---|
| *(Add name if using a real person)* | | | | | |

---

## 2. Model & Output Licences

| Component | Model / Tool | Licence / Terms | Commercial / Public Use Notes |
|---|---|---|---|
| Script & Translation | `gemini-3.8-flash`, `gemini-3.5-flash-lite` | Google Gemini API Terms of Service | Check Google AI Studio free-tier data retention/training terms; avoid sending sensitive private PII. |
| Narration (TTS) | `gemini-3.8-flash-tts` | Google Gemini API Terms of Service | Prebuilt voices (`Charon`) used without cloning a private individual. |
| Keyframes | `FLUX.2 klein 4B` (`flux-2-klein-4b`) | **Apache 2.0** (4B) / **Non-Commercial** (9B) | Use the **4B** Apache 2.0 model; avoid the 9B variant for commercial outputs. |
| Keyframes Fallback | `FLUX.1 schnell` | **Apache 2.0** | Permissive open-weight licence via Cloudflare Workers AI. |
| Moving Shots | `Wan 2.2 TI2V-5B` | **Apache 2.0** | Permissive open-weight licence. |
| Music / Score | `ACE-Step 1.5` | **MIT** | Trained on licensed, royalty-free, and synthetic data; outputs usable commercially. |
| Assembly | `FFmpeg` + `Pillow` | LGPL/GPL (FFmpeg binary) / HPND (Pillow) | Deterministic local post-production. |

---

## 3. AI Disclosure & Provenance Labelling Plan

1. **In-Film End Card**: Enabled in `storyboard.json` (`end_card.enabled = true`), rendering a visible 2.5-second `"Made with AI"` disclosure card with full model credits at the end of both `9:16` and `16:9` exports.
2. **Platform Disclosure**: When publishing on YouTube Shorts, TikTok, or Instagram Reels, switch the platform's **altered / synthetic AI content** label ON.
3. **Provenance & Style Ethics**:
   - Prompts describe visual qualities (`warm analog 35mm`, `natural morning light`, `wood texture`) rather than copying any living artist's name.
   - Any SynthID / C2PA watermarks emitted by upstream providers are preserved intact where applicable.
   - No private family addresses, phone numbers, or sensitive personal records are sent to free hosted endpoints.
