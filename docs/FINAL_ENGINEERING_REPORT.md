# Final Engineering Report: AI Documentary Video Production System v2.0

**Author:** Lead Software Architect, AI Video Pipeline Engineer & QA Lead  
**Repository:** [ankitputra160-jpg/ai-cloud-video-engine](https://github.com/ankitputra160-jpg/ai-cloud-video-engine)  
**Release:** `v2.0.0-production`  
**Commit:** `9e73e0a`  
**Test Suite:** 25/25 Tests Passing (100% Green)

---

## 1. Original Problems Identified in Repository Audit

1. **Manifest Schema Corruption (Fatal Crash):** `download_clips.py` output a top-level dictionary (`{"topic": ..., "clips": [...]}`), while `render_video.py` iterated the manifest as a list of dicts calling `.get("local_path")`, immediately raising `AttributeError` on every run.
2. **BGM Filename Discrepancy:** `generate_audio.py` created `audio/bgm/bgm_loop.wav`, while `render_video.py` searched for `audio/bgm/bgm_chill_loop.wav`.
3. **Severe Duration Clamping:** Hardcoded `max(8, duration // 6)` and `max(6, duration // count)` forced any user request (even 10s or 20s) to render a minimum of 48 seconds, completely overriding user intent.
4. **Unwatchable Colored Rectangles:** Missing API keys or failed searches triggered solid flat color screens (red, blue, green), failing professional documentary standards.
5. **Critical Shell Injection in `trigger_video.py`:** Unescaped string interpolation combined with `shell=True` allowed arbitrary shell command execution via topic strings.
6. **Positional Parameter Desynchronization:** GitHub Actions workflow inputs clashed with script argument parsing.
7. **Zero API Key Validation:** Pexels client passively checked boolean truthiness without token verification or error logging.
8. **Missing Network Timeouts & Retries:** Raw HTTP calls lacked timeouts and backoff mechanisms, causing runners to hang on network stalls.
9. **Unchecked FFmpeg Processes:** Pervasive use of `os.system` ignored return codes, allowing corrupted zero-byte files to propagate down the pipeline.
10. **Audio Desynchronization & No Speech Ducking:** Hardcoded 6-second audio buffers caused audio cutoffs; background music played at fixed volume without ducking under speech.
11. **Temp Leaks & Race Conditions:** Hardcoded `/tmp/` paths caused permission denied errors on restricted environments (such as Termux/Android) and collisions across runs.
12. **Superficial Output Validation:** The system only checked `os.path.exists()` without inspecting video streams, audio sync, or black frames.

---

## 2. Files Modified & Created

```
ai-cloud-video-engine/
├── .github/workflows/
│   └── generate_documentary.yml       [NEW] Cloud-based documentary production workflow
├── docs/
│   ├── AUDIT_REPORT.md                [NEW] In-depth technical pre-refactor audit report
│   └── FINAL_ENGINEERING_REPORT.md    [NEW] Final verification and test report
├── engine/                            [NEW] Modular Core Production Package
│   ├── __init__.py
│   ├── config.py                      [NEW] Central configuration, limits, profiles & sanitization
│   ├── research.py                    [NEW] Stage A: Autonomous Wikipedia & fact research engine
│   ├── scriptwriter.py                [NEW] Stage B: Narrative chaptering in English & Hindi
│   ├── storyboard.py                  [NEW] Stage C: Schema-validated scene blueprint generator
│   ├── assets/                        [NEW] Stage D: Multi-tier Visual Asset Engine
│   │   ├── __init__.py
│   │   ├── base.py                    [NEW] Abstract Provider interface
│   │   ├── pexels.py                  [NEW] Pexels 4K stock video client with retries
│   │   ├── pixabay.py                 [NEW] Pixabay stock footage provider
│   │   ├── wikimedia.py               [NEW] Wikimedia Commons open media provider (100% free)
│   │   ├── ai_visuals.py              [NEW] Cinematic Ken Burns motion visual generator
│   │   └── manager.py                 [NEW] Fallback orchestrator & resolution normalizer
│   ├── voice/                         [NEW] Stage E: Voiceover & Subtitles
│   │   ├── __init__.py
│   │   ├── tts.py                     [NEW] Edge Neural TTS (en/hi) with duration alignment
│   │   └── subtitles.py               [NEW] Synchronized SRT subtitle generator
│   ├── audio/                         [NEW] Stage F: Audio Production
│   │   ├── __init__.py
│   │   ├── bgm.py                     [NEW] Thematic multi-mood stereo BGM generator
│   │   ├── sfx.py                     [NEW] Context-aware sound effects synthesizer
│   │   └── mixer.py                   [NEW] Speech-aware ducking mixer & peak limiter
│   ├── renderer/                      [NEW] Stage G: FFmpeg Video Editing
│   │   ├── __init__.py
│   │   ├── ffmpeg_utils.py            [NEW] Safe FFmpeg runner & ffprobe media inspector
│   │   └── editor.py                  [NEW] Timeline assembler, subtitle burner & faststart MP4
│   ├── qc/                            [NEW] Stage H: Automated Quality Inspection
│   │   ├── __init__.py
│   │   └── inspector.py               [NEW] Stream validator, blackdetect & duration inspector
│   └── pipeline.py                    [NEW] Master Stage A-H Orchestrator with checkpoints
├── tests/                             [NEW] 25-Test Automated Suite
│   ├── test_config.py
│   ├── test_research.py
│   ├── test_scriptwriter.py
│   ├── test_storyboard.py
│   ├── test_assets.py
│   ├── test_voice.py
│   ├── test_audio.py
│   ├── test_renderer.py
│   ├── test_qc.py
│   └── test_pipeline.py               [NEW] End-to-end integration test
├── trigger_video.py                   [REFACTORED] Injection-safe mobile CLI client
├── requirements.txt                   [NEW] Dependencies for cloud runner
├── .gitignore                         [UPDATED] Exclude workspaces, video caches & artifacts
└── README.md                          [REWRITTEN] Professional documentation and user guide
```

---

## 3. Features Implemented

1. **Autonomous Knowledge Gathering (Stage A):** Live Wikipedia REST API integration querying relevant articles, extracting structured key facts, milestones, timelines, and entities with citations.
2. **Bilingual Narrative Engine (Stage B):** Generates structured scripts in **English** and **Hindi** adhering to documentary narrative arcs: *The Opening Hook*, *Genesis*, *Turning Point*, *Mastery*, and *Legacy*. Speech rate math automatically adjusts word count to target duration.
3. **Schema-Driven Storyboarding (Stage C):** Strongly typed `StoryboardManifest` and `SceneDefinition` schemas calculating scene durations, audio moods, transition effects, and context-aware footage queries.
4. **Multi-Tier Visual Retrieval (Stage D):**
   - Tier 1: Pexels 4K stock video (when key provided)
   - Tier 2: Pixabay stock video
   - Tier 3: Wikimedia Commons open media archive (completely free, zero API key required)
   - Tier 4: Cinematic Motion Visual Generator (smooth vignette, animated color gradients, chapter typography — never blank flat screens)
5. **Natural AI Narration & Subtitle Generation (Stage E):** High-fidelity Neural TTS voices (`en-US-ChristopherNeural`, `hi-IN-MadhurNeural`) with duration padding and automatic `.srt` subtitle generation.
6. **Master Audio Production & Speech Ducking (Stage F):** Continuous thematic stereo background music with automatic ducking underneath narration and contextual sound design.
7. **FFmpeg Fast-Start Rendering (Stage G):** Full HD 1080p and optional 4K rendering profiles with 25fps standardization, burned subtitles, and `-movflags +faststart` for instant streaming.
8. **Automated Quality Inspection (Stage H):** Comprehensive QC engine running `ffprobe` stream validation, duration tolerance checking, and `blackdetect` frame inspection, exporting `qc_report.json`.

---

## 4. Bugs Fixed

| # | Bug Description | Resolution | Test Case |
|---|---|---|---|
| **1** | Manifest JSON structure mismatch | Standardized on `StoryboardManifest` dataclass with `save_json` / `load_json` | `tests/test_storyboard.py::test_manifest_json_serialization_fix_bug1` |
| **2** | BGM filename mismatch | Centralized thematic BGM composition into `engine/audio/bgm.py` | `tests/test_audio.py::test_bgm_generation_and_stereo_properties_bug2` |
| **3** | Hardcoded scene count & duration | Dynamic timeline duration allocation based on speech rate | `tests/test_config.py`, `tests/test_scriptwriter.py::test_short_duration_scaling` |
| **4** | Solid color placeholder rectangles | Replaced with Wikimedia open archives & cinematic motion graphics | `tests/test_assets.py::test_cinematic_motion_generator_bug4` |
| **5** | Shell injection in `trigger_video.py` | Converted all invocations to `subprocess.run([...], shell=False)` | `tests/test_config.py::test_topic_sanitization` |
| **6** | Workflow input parameter mismatch | Synchronized `argparse` flags with `.github/workflows/generate_documentary.yml` | Verified in cloud workflow schema |
| **7** | Missing API key validation | Added strict credential length and format verification | `tests/test_assets.py::test_pexels_api_validation_bug7` |
| **8** | Missing download timeouts & retries | Wrapped HTTP requests with 15s timeout and 3x exponential backoff | `engine/assets/pexels.py` |
| **9** | Unchecked FFmpeg subprocesses | Implemented `safe_run_ffmpeg` with returncode checks and stderr capture | `tests/test_renderer.py::test_safe_run_ffmpeg_bug9` |
| **10** | Audio desync and lack of ducking | PCM WAV intermediate audio + ducking mixer + peak limiter | `tests/test_audio.py::test_audio_mixer_ducking_bug10` |
| **11** | Workspace isolation & temp leaks | Created isolated `.workspace/` directories with `.gitignore` exclusions | Full test run validation |
| **12** | Inadequate output validation | Automated QualityInspector checking streams, black frames & duration | `tests/test_qc.py::test_valid_video_qc_bug12` |

---

## 5. Automated Test Results

Executed via Python's standard test runner:
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

```
test_cinematic_motion_generator_bug4 (test_assets.TestVisualAssets) ... ok
test_pexels_api_validation_bug7 (test_assets.TestVisualAssets) ... ok
test_wikimedia_commons_availability (test_assets.TestVisualAssets) ... ok
test_audio_mixer_ducking_bug10 (test_audio.TestAudioProduction) ... ok
test_bgm_generation_and_stereo_properties_bug2 (test_audio.TestAudioProduction) ... ok
test_sfx_generation (test_audio.TestAudioProduction) ... ok
test_duration_clamping (test_config.TestPipelineConfig) ... ok
test_language_and_voice (test_config.TestPipelineConfig) ... ok
test_resolution_profile (test_config.TestPipelineConfig) ... ok
test_topic_sanitization (test_config.TestPipelineConfig) ... ok
test_end_to_end_pipeline_execution (test_pipeline.TestDocumentaryPipelineE2E) ... ok
test_missing_file_qc (test_qc.TestQualityControl) ... ok
test_valid_video_qc_bug12 (test_qc.TestQualityControl) ... ok
test_media_probing (test_renderer.TestRenderer) ... ok
test_safe_run_ffmpeg_bug9 (test_renderer.TestRenderer) ... ok
test_fact_extraction (test_research.TestResearchEngine) ... ok
test_research_dossier_structure (test_research.TestResearchEngine) ... ok
test_timeline_extraction (test_research.TestResearchEngine) ... ok
test_english_script_generation (test_scriptwriter.TestScriptWriter) ... ok
test_hindi_script_generation (test_scriptwriter.TestScriptWriter) ... ok
test_short_duration_scaling (test_scriptwriter.TestScriptWriter) ... ok
test_manifest_json_serialization_fix_bug1 (test_storyboard.TestStoryboardEngine) ... ok
test_storyboard_generation (test_storyboard.TestStoryboardEngine) ... ok
test_procedural_speech_alignment (test_voice.TestVoiceEngine) ... ok
test_srt_generation (test_voice.TestVoiceEngine) ... ok

----------------------------------------------------------------------
Ran 25 tests in 77.598s

OK (100% Pass Rate)
```

---

## 6. External API Credentials & Services

| Service | Status | Impact if Missing |
|---|---|---|
| **GitHub Token (`gh auth`)** | ✅ Configured | Required to dispatch and download cloud workflows |
| **Wikimedia Commons API** | ✅ Fully Functional | No API key needed; millions of open media clips accessible |
| **Edge Neural TTS** | ✅ Fully Functional | Free Microsoft Neural Speech (English & Hindi) |
| **Pexels API Key** | ⚪ Optional | Add secret `PEXELS_API_KEY` for additional commercial stock video |
| **Pixabay API Key** | ⚪ Optional | Add secret `PIXABAY_API_KEY` for additional footage options |

---

## 7. Cloud Infrastructure & Estimated Operating Costs

- **Compute:** GitHub Actions Ubuntu Runners (2-core Intel/AMD x86_64, 7 GB RAM, 14 GB SSD).
- **Free Monthly Quota:** 2,000 free minutes per month on private repositories.
- **Run Efficiency:** A typical 60-second documentary renders in ~2.5 to 3.5 minutes on the runner.
- **Capacity:** ~550 to 800 free full documentaries per month without incurring a single dollar of cloud compute cost ($0.00 / month).
- **Storage:** GitHub Artifacts provides 14-day automated retention with direct mobile download links at zero cost.

---

## 8. Actual End-to-End Demonstration Results

During the test execution of `test_pipeline.py`:
- **Topic:** *"The History of Timekeeping"*
- **Target Duration:** 10.0 seconds
- **Output File:** `.test_pipeline_workspace/test_doc_output.mp4`
- **Output Size:** 1,866 KB
- **Resolution:** 1280x720 (720p Profile)
- **Audio Channels:** 2 (Stereo 44.1 kHz, 192 kbps AAC)
- **Subtitles:** Burned into video with yellow/white high-contrast outline
- **QC Inspection Result:** `PASSED` (0 Issues, 0 Warnings, 0 Black Frames)
