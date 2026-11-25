# 🎬 AI Documentary Video Production Engine v2.0

> A fully automated, cloud-based AI Documentary Video Production System.
> Submit any topic from your mobile phone — the entire research, scriptwriting, storyboarding, visual asset retrieval, narration, sound design, FFmpeg rendering, and quality control executes in the cloud.

---

## 🌟 Key Capabilities

- 📱 **Mobile-First Client:** Submit topics, monitor progress, and download finished documentaries with a single command or GitHub Web UI. Zero rendering computation on mobile.
- 🔬 **Stage A: Autonomous Research:** Dynamic factual research from Wikipedia and open knowledge bases with source tracking and timeline extraction.
- ✍️ **Stage B: Narrative Scriptwriting:** Automatic structure generation (Opening Hook, Genesis, Breakthrough, Mastery, Climax, Legacy) in **English** and **Hindi**.
- 📋 **Stage C: Dynamic Storyboard:** Scene-by-scene schemas with visual prompts, transition cues, duration scaling, and subtitle alignments.
- 🎥 **Stage D: Multi-Tier Visual Retrieval:**
  - Pexels 4K/HD stock footage
  - Pixabay stock video
  - Wikimedia Commons public domain & CC media archives (100% free, no API key needed!)
  - Cinematic Motion Graphic Generator (smooth Ken Burns motion, atmospheric lighting, vignette, and typography — never blank colored placeholders)
- 🎙️ **Stage E: Natural AI Voiceover & Subtitles:** Edge Neural TTS in English (`en-US-ChristopherNeural`) and Hindi (`hi-IN-MadhurNeural`) with duration alignment and automatic `.srt` subtitle generation.
- 🎵 **Stage F: Audio Production & Ducking:** Thematic musical harmonies matched to chapter mood, scene sound effects, and speech-aware music ducking.
- 🎞️ **Stage G: FFmpeg Assembly:** Frame rate stabilization (25fps), resolution normalization (1080p Full HD & optional 4K), subtitle burning, and faststart MP4 output.
- 🛡️ **Stage H: Automated Quality Inspection (QC):** Full stream validation, duration tolerance checking, black frame detection (`blackdetect`), and certified `qc_report.json`.

---

## 🏗️ System Architecture

```
Mobile Phone (Controller)
       │
       ▼ (trigger_video.py / GitHub API)
GitHub Actions Cloud Runner (Ubuntu Latest)
       │
       ├─► Stage A: Topic Research (Wikipedia API / Knowledge Bases)
       ├─► Stage B: Scriptwriter (Chaptering, Pacing & Word Count)
       ├─► Stage C: Storyboard Engine (Scene Specs & Queries)
       ├─► Stage D: Visual Asset Manager (Pexels / Pixabay / Commons / Motion Canvas)
       ├─► Stage E: Voiceover & Subtitle Engine (Neural TTS, SRT Sync)
       ├─► Stage F: Audio Production (BGM Harmonies, SFX, Speech Ducking)
       ├─► Stage G: FFmpeg Video Editor (Assembly, Subtitle Burn, 1080p/4K)
       └─► Stage H: Quality Control Inspector (Integrity, Blackframe, Duration Checks)
       │
       ▼ (Automated Artifact Upload)
Mobile Download / Gallery Delivery
```

---

## 🚀 Quick Start (Mobile Trigger)

### 1. Submit from Mobile Terminal
Run the injection-safe mobile trigger script:

```bash
# English 60-second Documentary (1080p Full HD)
python3 trigger_video.py --topic "The Secrets of the Indus Valley Civilization" --language en --duration 60 --resolution 1080p

# Hindi 60-second Documentary
python3 trigger_video.py --topic "प्राचीन भारतीय खगोल विज्ञान का इतिहास" --language hi --duration 60 --resolution 1080p

# Short 15-second Quick Documentary
python3 trigger_video.py --topic "Origins of the Steam Engine" --language en --duration 15
```

The script triggers GitHub Actions in the cloud, monitors progress in real-time, and automatically downloads the finished `.mp4` directly to your phone's storage.

### 2. Trigger via GitHub Web UI
1. Go to **Actions** → **🎬 AI Documentary Video Production Pipeline**
2. Click **Run workflow**
3. Select Topic, Language (`en` or `hi`), Duration (10 - 600s), and Resolution
4. Click **Run workflow**

---

## 🧪 Automated Test Suite

The engine includes a dedicated 25-test suite covering unit tests and end-to-end integration:

```bash
# Run all tests
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### Test Coverage Summary:
- `tests/test_config.py`: Parameter validation, duration bounds, shell sanitization.
- `tests/test_research.py`: Wikipedia parsing, timeline & entity extraction.
- `tests/test_scriptwriter.py`: English & Hindi chapter composition, pacing.
- `tests/test_storyboard.py`: Schema validation, JSON serialization (**Fix for Bug 1**).
- `tests/test_assets.py`: Provider hierarchy, Pexels validation (**Bug 7/8**), Motion Visuals (**Bug 4**).
- `tests/test_audio.py`: Stereo BGM (**Bug 2**), SFX synthesis, Speech Ducking (**Bug 10**).
- `tests/test_voice.py`: Speech tempo alignment, SRT timestamp generation.
- `tests/test_renderer.py`: Safe FFmpeg process wrapper (**Bug 9**), media probe.
- `tests/test_qc.py`: Stream inspection, black frame detection (**Bug 12**).
- `tests/test_pipeline.py`: Full end-to-end documentary production and verification.

---

## ⚙️ Configuration & Environment Variables

| Variable | Description | Required? |
|---|---|---|
| `PEXELS_API_KEY` | Pexels Video API Key (Free tier: 200 req/hr) | Optional (Commons & Motion Graphics used if unset) |
| `PIXABAY_API_KEY` | Pixabay API Key | Optional |
| `GITHUB_TOKEN` | GitHub CLI authentication token | Required for `gh` triggering |

Add optional keys in repository settings:  
👉 `Settings → Secrets and variables → Actions → New repository secret`

---

## 📁 Repository Structure

```
ai-cloud-video-engine/
├── .github/workflows/
│   └── generate_documentary.yml  # Cloud GitHub Actions workflow
├── engine/                       # Core Documentary Package
│   ├── config.py                 # Configuration & limits
│   ├── research.py               # Stage A: Research
│   ├── scriptwriter.py           # Stage B: Scriptwriting
│   ├── storyboard.py             # Stage C: Storyboarding
│   ├── assets/                   # Stage D: Visual Assets (Pexels, Commons, Motion)
│   ├── voice/                    # Stage E: Voiceover & Subtitles
│   ├── audio/                    # Stage F: Audio Production & Ducking
│   ├── renderer/                 # Stage G: FFmpeg Video Editor
│   ├── qc/                       # Stage H: Automated Quality Control
│   └── pipeline.py               # Master Orchestrator
├── tests/                        # Automated Test Suite (25 Tests)
├── docs/                         # Technical Audit & Architecture Reports
│   └── AUDIT_REPORT.md           # 12 Critical Bugs & Technical Audit
├── trigger_video.py              # Hardened Mobile Trigger CLI
├── requirements.txt              # Cloud Runner Dependencies
└── README.md
```

---

## 📄 License
MIT License. Built for autonomous AI media production.
