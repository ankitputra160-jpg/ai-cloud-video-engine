# 🎬 AI Documentary Video Production Engine v3.0

> A fully autonomous, modular AI Documentary Video Production System (Dhruv Rathee pacing + expressive Hinglish storytelling).  
> Run from your mobile phone on **Google Colab GPU (L4 / T4)** or **GitHub Actions**, with crash-proof Google Drive checkpointing and 1080p/4K Faststart + Auto-Thumbnail delivery.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ankitputra160-jpg/ai-cloud-video-engine/blob/main/colab_documentary_engine.ipynb)

---

## 🌟 v3.0 Key Upgrades

1. **Fact-Proof Multi-Source Research (`engine/research.py`):** Wikipedia (`EN -> HI`), Wikidata, DuckDuckGo, Google News RSS, and `Trafilatura` clean scraping → locks `fact_sheet.json`.
2. **Spontaneous 3-Pass Hinglish Script + `HindiHumanizerCritic` (`engine/scriptwriter.py`, `engine/text/humanizer.py`):**
   - Local **Gemma-3-12B/27B** (`llama.cpp`) default + optional Gemini/Groq APIs (chapter-batched up to 25 minutes).
   - Inspired by `blader/humanizer`: purges textbook AI words (`महज़`, `निष्कर्षतः`, `पुनरीक्षण`) and places Pattern Interrupts every 35–40s.
3. **Dual-Layer `Speak vs. Show` Span-ID Sync (`engine/text/pronunciation.py`, `engine/voice/aligner.py`, `engine/voice/subtitles.py`):**
   - TTS receives spoken Devanagari (`"पाँच सौ करोड़ रुपये"`, `"सुप्रीम कोर्ट"`), while subtitles display `"₹500 Cr"` and `"Supreme Court"` synced via **`ctc-forced-aligner` (`facebook/mms-300m`)** with Span-ID chunk locking.
4. **Expressive Prosody (`Emotion Tag Router` + 4-Mood Bank):**
   - Parses `[pause:Xs]`, `[fear]`, `[angry]`, `[slow]`, `[fast]` cleanly → sample-rate-safe FFmpeg DSP + room-tone silence → `IndicF5` / `Indic Parler-TTS` / `Qwen3-TTS` / `Sarvam` / `ElevenLabs` / `Edge` / `Piper`.
   - Self-bootstraps 4 copyright-free mood clips (`ref_neutral`, `ref_suspense`, `ref_angry`, `ref_fast`) once onto Google Drive.
5. **Hybrid `45:25:25:5` Visuals & Static Hindi Safety:**
   - **Real Sources (45%):** PIB India, Internet Archive, Openverse, Wikimedia Commons, NASA, Pexels, Pixabay + `OpenCLIP` semantic check + Ken Burns + subtle film grain.
   - **2D Investigative Cards (25%):** Playwright HTML/CSS Newspaper Cuttings with animated yellow highlighter sweep, `rembg` Quote Cards, and Map/Stat Cards.
   - **AI Visuals (25% Still + 5% Hero I2V):** `FLUX.1-schnell` (anti-virtual camera prompt) + `LTX-Video 0.9.7-distilled FP8` strictly on Hero Hooks.
   - Static hinted `NotoSansDevanagari` TTFs + `libass` + zero FFmpeg `drawtext` on Hindi text.
6. **Hardware `h264_nvenc`, Checkpoint Resume & Auto-Thumbnail (`engine/checkpoint.py`, `engine/renderer/`):**
   - Audio-First `0.001s` timing lock (zero frame drift), Google Drive auto-resume, `-14 LUFS LRA=6` audio mastering, `sidechaincompress` CC0 BGM bank, real Foley SFX, `AutoThumbnailGenerator`, and GitHub Releases 2 GB upload.

---

## ☁️ Google Colab Quick Start

1. Open [colab_documentary_engine.ipynb](https://colab.research.google.com/github/ankitputra160-jpg/ai-cloud-video-engine/blob/main/colab_documentary_engine.ipynb) in Colab (**Runtime → Change runtime type → L4 or T4 GPU**).
2. Add your Hugging Face token (`HF_TOKEN`) in Colab Secrets (🔑) after accepting terms for `ai4bharat/IndicF5` & `black-forest-labs/FLUX.1-schnell` (plus optional `GEMINI_API_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY`, `ELEVENLABS_API_KEY`).
3. Run **Step 1** (setup), **Step 2** (Mount Google Drive + cache CC0 BGM bank), and **Step 3** (Enter Topic → Generate!).

---

## 🧪 Automated Test Suite

```bash
PYTHONPATH=. python3 -W error::SyntaxWarning -m unittest discover -s tests -p "test_*.py" -v
```

Legacy engine backup is preserved safely on GitHub branch & tag **`backup-v1`**.

## 📄 License
MIT License.
