# 🎬 AI Cloud Documentary Engine — Master Architecture Blueprint (v3.0)

**Version:** 3.0 (Dhruv Rathee Style Hybrid Documentary + Expressive Indic Storytelling)  
**Target Runtimes:** Google Colab (L4 24GB / T4 15GB VRAM + High-RAM) & GitHub Actions CPU (`backup-v1` preserved on branch/tag `backup-v1`)  
**Scope:** 10-second shorts up to 25-minute (1500s) Hindi/Hinglish & English documentaries with human conversational voiceover, word-synced dual-layer subtitles, watermark-free archival/news/AI visuals, and crash-proof Google Drive checkpointing.

---

## 1. Core Design Philosophy (Non-Negotiables)
1. **No Automated Slideshow:** Visuals change every **3–5 seconds** (~250–350 visual beats in a 20-min video) following **45% Real Photos + Ken Burns : 25% Playwright News/Map Cards : 25% AI Still Images : 5% Hero I2V Clips**.
2. **Spontaneous Thinking-Out-Loud Hinglish Script (Anti-Bookish Hindi):** Break long essays into 12–16s spoken beats (`~18–25 words` per voice chunk, `8–12 words` per sentence) with **Pattern Interrupts every 35–40 seconds** (direct viewer questions, twists, open loops).
3. **Audio-First Timing Lock (Zero Frame Drift):** Voice synthesis runs **before** visual clip cutting (`0.001s` float precision via `ffprobe`/`wave` + frame alignment), eliminating cumulative audio-video drift.
4. **Dual-Layer `Speak vs. Show` Sync (`Span-ID Mapping`):**
   - `speak`: Clean Devanagari phonetic words for Hindi TTS (`"पाँच सौ करोड़ रुपये"`, `"सुप्रीम कोर्ट"`, `"सी जे आई"`).
   - `show`: Compact, scannable Hinglish/numeric subtitles (`"₹500 Cr"`, `"Supreme Court"`, `"CJI"`, `"45%"`, `"2026"`).
   - Synced via **`ctc-forced-aligner` (`facebook/mms-300m`, `language="hin"`, `romanize=True`)** and chunk-locked so a `span_id` never splits across subtitle lines.
5. **Expressive Human Prosody (`Emotion Tag Router`):**
   - Supported inline tags: `[pause:0.5s]`, `[fear]...[/fear]`, `[angry]...[/angry]`, `[slow]...[/slow]`, `[fast]...[/fast]` (max 1–2 shifts per thought group).
   - Never pass tags into TTS directly; route each segment to the matching mood profile, insert natural low-floor digital room silence (`-65dB`) for `[pause]`, apply FFmpeg `asetrate+aresample+atempo` at each clip's actual sample rate, stitch with 20ms crossfades, and strip tags prior to forced alignment.
6. **Zero Devanagari Matra Corruption:**
   - Replace `NotoSansDevanagari-VF.ttf` priority with **Static TTFs** (`NotoSansDevanagari-Bold.ttf`, `NotoSansDevanagari-Regular.ttf`, `NotoSansDevanagari-SemiBold.ttf`).
   - Use **Unicode NFC + `regex` `\X` grapheme wrapping**, `libass` (`ass=...:fontsdir=...`) for subtitles, and **Playwright / Pillow+raqm** for cards/badges (ban FFmpeg `drawtext` on Devanagari).
7. **Strict Stage-Gate VRAM Unloading + Google Drive Checkpointing:**
   - Colab models (`Gemma-3`, `IndicF5`, `MMS-300M`, `OpenCLIP`, `FLUX.1-schnell`, `LTX-Video`) never stay co-resident in VRAM. Load → execute → `del model; gc.collect(); torch.cuda.empty_cache()`.
   - Persist stage artifacts (`fact_sheet.json`, `script.json`, `storyboard.json`, `audio/`, `assets/`, `rendered_scenes/`) in Google Drive so disconnected sessions resume cleanly.

---

## 2. The 6-Module Architecture Flow

1. **Module 1 — `ResearchAgent` (`engine/research.py`)**
   - Multi-source collection: Wikipedia (`EN -> HI` langlinks), Wikidata, DuckDuckGo (`ddgs`), **`Trafilatura`** clean full-article scraping, and **RSS Feeds** (Google News / The Hindu / Indian Express / LiveLaw).
   - Outputs locked **`fact_sheet.json`** (dates, verified events, direct quotes, source URLs, entities). Scriptwriter is strictly anchored to verified facts.
2. **Module 2 — `HookAndBeatArchitect` (`engine/storyboard.py`)**
   - Generates opening 30s Hook + chapter structure + 3–5s `VisualBeat` sequences (`real_photo`, `news_card`, `quote_card`, `map_card`, `stat_card`, `ai_image`, `hero_i2v`).
   - Enforces **35–40s Pattern Interrupts**, English search/CLIP queries (`visual_prompt_en`), and anti-virtual documentary prompt styling.
3. **Module 3 — `SpontaneousScriptwriter` (`engine/scriptwriter.py` + `engine/llm_client.py`)**
   - Default Free Mode: **Local `Gemma-3-12B-IT` (T4) / `Gemma-3-27B-IT` (L4)** GGUF via `llama.cpp` with JSON schema grammar; Optional Cloud APIs: `GEMINI_API_KEY` / `GROQ_API_KEY`; Deterministic conversational Hinglish fallback for offline CPU tests.
   - **3-Pass Batching** (50 beats / chapter batch, works cleanly up to 25 minutes instead of skipping >30 scenes!):
     - Pass 1: Schema + `fact_sheet.json` alignment + Pattern Interrupt placement.
     - Pass 2: Conversational Hinglish draft + inline emotion/pause tags.
     - Pass 3: Spoken rhythm & rewrite audit.
4. **Module 4 — `HindiHumanizerCritic` & `PronunciationNormalizer` (`engine/text/humanizer.py`, `engine/text/pronunciation.py`)**
   - Inspired by **`blader/humanizer`** (Wikipedia *Signs of AI Writing* adapted to spoken Hindi/Hinglish):
     - Scans & flags/replaces stiff AI words (*"महज़"*, *"निष्कर्षतः"*, *"अत्यंत महत्वपूर्ण"*, *"सर्वविदित है"*, *"गौरतलब है कि"*, *"पुनरीक्षण"*, *"परिलक्षित"*, *"अनियमितताओं"*, *"आने वाला वक्त ही बताएगा"*) and `"न केवल X, बल्कि Y"` templates.
     - Enforces short spoken bursts (`<= 22 words` per beat) and natural connectors (*"ज़रा सोचिए..."*, *"अब यहीं असली पेंच फँसता है..."*).
   - `PronunciationNormalizer`: Generates paired **`span_id` Speak/Show tokens** (Indian numerals/years/percentages/crore-lakh/acronyms → spoken Devanagari words vs. compact subtitle strings).
5. **Module 5 — `VoiceDirector`, `Aligner`, & `AudioMaster` (`engine/voice/`, `engine/audio/`)**
   - **Reference Bank (`ensure_mood_reference_bank`):** Bootstraps 4 copyright-free studio clips (`ref_neutral.wav`, `ref_suspense.wav`, `ref_angry.wav`, `ref_fast.wav`) once via `ai4bharat/indic-parler-tts` (saved to Drive, user-replaceable anytime).
   - **TTS Engines:** `IndicF5` (primary 1.8GB Flow-Matching + 4-mood bank + 15–20s chunks + cache clear every 25 chunks), `Indic Parler-TTS`, `Qwen3-TTS`, optional `Sarvam AI (Bulbul v4)` / `ElevenLabs`, `Edge-TTS` / `Piper` fallback.
   - **Emotion Router:** Parses 5 inline tags, inserts room-toned silence, applies rate-safe FFmpeg prosody DSP, crossfades at 20ms.
   - **Forced Aligner + Subtitles:** `ctc-forced-aligner` (`mms-300m`, `hin`) aligns `speak` tokens → maps exact timestamps to `show` spans (`span_id` chunk-locked, 3–5 words, <= 30 chars) → exports `.ass` & `.srt`.
   - **Audio Mastering & Foley:**
     - Voice chain: `acompressor=threshold=-18dB:ratio=3:attack=5:release=50,equalizer=f=180:width_type=h:width=100:g=2,loudnorm=I=-14:TP=-1.5:LRA=6`.
     - Optional archive radio filter (`highpass=f=300,lowpass=f=3000`) on historical quotes.
     - 4-Mood CC0 BGM Bank cached in Google Drive (`investigative_pulse`, `somber_emotional`, `historical_epic`, `neutral_explainer`) with `acrossfade=d=2` + **`sidechaincompress=threshold=0.02:ratio=6:attack=50:release=400`**.
     - Real Foley SFX (`assets/sfx/`: `soft_whoosh`, `paper_rustle`, `marker_stroke`, `subtle_pop`, `deep_sub_hit`, `camera_click`) triggered by `visual_type`.
6. **Module 6 — `VisualDirector`, `QC`, `Editor`, & `Thumbnail` (`engine/assets/`, `engine/renderer/`, `engine/qc/`)**
   - **Watermark-Free Sources:** **PIB India (`pib.gov.in`)**, **Internet Archive (`archive.org`)**, **Openverse (`api.openverse.org`)**, **Wikimedia Commons**, **NASA**, plus optional Pexels/Pixabay.
   - **Visual QC:** Min resolution/16:9 orientation filter + **Colab `OpenCLIP ViT-B-32`** semantic score check against `visual_prompt_en` (auto-rejects mismatched photos).
   - **2D Investigative Cards (Playwright / Pillow+raqm):** Newspaper texture + RSS headline + animated yellow highlighter sweep (`clip-path`) + `rembg` portrait quote cards + interactive SVG/MapLibre location cards.
   - **AI Visual Fallback:**
     - `FLUX.1-schnell` (FP8, 4-step) with Anti-Virtual documentary camera/lens/grain prompt & negative prompt (`3d render, cgi, plastic skin, neon`).
     - `LTX-Video 0.9.7-distilled` FP8 Image-to-Video (`8n+1` frames, 3s) reserved strictly for ~5% Hero Hooks & Chapter Openings.
   - **Rendering & Delivery:** FFmpeg `h264_nvenc` (safe `2` concurrent workers) or `libx264`, `-pix_fmt yuv420p -movflags +faststart`, **Auto-Thumbnail (`thumbnail.jpg`)**, Drive checkpoint resume, and optional `gh release create` upload for GitHub Actions (>100MB safe, never commit `.mp4` to Git).

---

## 3. Backward Compatibility Guarantee
All existing CLI flags and workflow dispatch parameters on `trigger_video.py`, `.github/workflows/generate_documentary.yml`, `colab_documentary_engine.ipynb`, and `engine.pipeline` (`--topic`, `--style`, `--duration`, `--language`, `--resolution`, `--subtitle-style`, `--voice-engine`, `--storyboard-file`, `--output`, `--work-dir`) remain 100% intact. New capabilities are exposed purely as optional flags/env vars/secrets.
