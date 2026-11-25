# Technical Audit Report: AI Cloud Video Engine

**Author:** Lead Software Architect & QA Engineer  
**Date:** November 25, 2026  
**Repository:** [ankitputra160-jpg/ai-cloud-video-engine](https://github.com/ankitputra160-jpg/ai-cloud-video-engine)  
**System Status:** Pre-refactor Audit

---

## 1. Executive Summary

A comprehensive architectural and code-level audit was conducted on the `ai-cloud-video-engine` repository. The existing codebase comprises three primary scripts (`download_clips.py`, `generate_audio.py`, `render_video.py`), one mobile trigger utility (`trigger_video.py`), and a GitHub Actions workflow (`generate_video.yml`).

While the repository successfully demonstrated basic repository setup and GitHub Actions connectivity, the codebase suffers from severe architectural fragility, fatal runtime bugs, security vulnerabilities (shell injection), hardcoded mock behaviors, and an absence of genuine documentary generation capabilities.

This report documents all 12 critical bugs identified, assesses the gap between current state and production documentary requirements, and establishes the blueprint for the upgraded modular engine.

---

## 2. Detailed Findings: 12 Critical Bugs

### Bug 1: Manifest JSON Structure Mismatch (Fatal Crash)
* **Location:** `scripts/download_clips.py` (L95-96) vs `scripts/render_video.py` (L150-155)
* **Root Cause:**
  `download_clips.py` serializes a dictionary:
  ```python
  json.dump({"topic": topic, "clips": clips_downloaded, "count": len(clips_downloaded)}, f)
  ```
  `render_video.py` assumes the root is a list of scene dictionaries:
  ```python
  for item in manifest:
      clips.append(item.get("local_path", ""))
  ```
* **Impact:** In Python, iterating over a dictionary iterates over its keys (`"topic"`, `"clips"`, `"count"`). Calling `"topic".get(...)` immediately raises `AttributeError: 'str' object has no attribute 'get'`, crashing the renderer on every run when `manifest.json` is present.
* **Resolution:** Standardize on a strongly-typed `StoryboardManifest` schema with dataclasses.

### Bug 2: BGM Filename Discrepancy
* **Location:** `scripts/generate_audio.py` (L149) vs `scripts/render_video.py` (L178)
* **Root Cause:** `generate_audio.py` writes `audio/bgm/bgm_loop.wav`, while `render_video.py` hardcodes an expectation for `audio/bgm/bgm_chill_loop.wav`.
* **Impact:** The renderer fails to find the primary BGM file, forcing a glob fallback or resulting in silent videos if directory structures vary.
* **Resolution:** Establish centralized asset path constants in `config.py`.

### Bug 3: Incorrect Scene Count and Duration Clamping
* **Location:** `download_clips.py` (L67) and `render_video.py` (L166-167)
* **Root Cause:** `download_clips.py` clamps clips to `max(8, duration // 6)`. `render_video.py` clamps `clip_duration = max(6, args.duration // scene_count)`.
* **Impact:** If a user requests a 10-second or 30-second test video, the system forces 8 scenes of 6 seconds each, rendering a 48-second video. User duration parameters are effectively overridden and ignored.
* **Resolution:** Implement dynamic scene timeline allocation based on narration word count, speech cadence, and total target duration.

### Bug 4: Incorrect Handling of Missing Clips (Colored Rectangles)
* **Location:** `download_clips.py` (L51-57, 90-92) and `render_video.py` (L204-206)
* **Root Cause:** When an API key is missing or a query returns zero results, the engine generates solid color test rectangles (red, blue, green) using FFmpeg `lavfi color`.
* **Impact:** Produces unwatchable, amateur placeholder screens violating the core documentary requirement.
* **Resolution:** Implement a resilient multi-tier visual provider manager:
  1. Stock video (Pexels / Pixabay)
  2. Open licensed historical archives (Wikimedia Commons)
  3. Dynamic AI visuals with smooth Ken Burns motion (pan/zoom) and depth effects.

### Bug 5: Critical Security Vulnerability: Shell Injection in `trigger_video.py`
* **Location:** `trigger_video.py` (L21-26, 34-40, 85)
* **Root Cause:** Commands are constructed using raw string formatting with `shell=True`:
  ```python
  cmd = f'gh workflow run {WORKFLOW} --repo {REPO} -f topic="{topic}" -f style="{style}" -f duration="{duration}"'
  subprocess.run(cmd, shell=True, ...)
  ```
* **Impact:** Any topic containing characters like `"$(...)`, `&&`, `;`, or `` ` `` allows arbitrary command execution on the host machine.
* **Resolution:** Refactor all `subprocess` invocations to list arguments (`shell=False`) with strict parameter validation and escaping.

### Bug 6: Workflow Input Parameter Mismatch
* **Location:** `.github/workflows/generate_video.yml`
* **Root Cause:** Discrepancy between positional CLI argument expectations and flag options (`--topic`, `--style`, `--duration`).
* **Impact:** Script crashes or ignores workflow inputs during GitHub Actions execution.
* **Resolution:** Synchronize workflow parameter names with `argparse` definitions across all pipeline stages.

### Bug 7: Missing API Key Validation and Pre-flight Checks
* **Location:** `scripts/download_clips.py` (L34-36)
* **Root Cause:** `search_pexels` passively checks `if not PEXELS_API_KEY: return None`. There is no format check, token verification, or clear user notification of why an API call was bypassed.
* **Impact:** Silent degradation into fallback behavior with no diagnostic logging for the user.
* **Resolution:** Pre-flight credential verification with structured diagnostic reports.

### Bug 8: Missing Network Timeouts, Retries, and Exponential Backoff
* **Location:** `download_clips.py` (L27-32)
* **Root Cause:** `requests.get(url, stream=True)` contains no `timeout` parameter. Network stalls can freeze the GitHub Actions runner until the 20-minute job timeout is reached.
* **Impact:** Wasted GitHub Actions minutes, hung workflows, and no resilience against transient network blips or HTTP 429 rate limits.
* **Resolution:** Implement a robust HTTP client wrapper with configured connect/read timeouts, exponential backoff (retries=3), and status code handling.

### Bug 9: Unchecked FFmpeg Subprocess Executions
* **Location:** `download_clips.py` (L82, 55) and `render_video.py` (L50)
* **Root Cause:** Widespread use of `os.system()` where return codes are discarded. In `render_video.py`, several `subprocess.run` calls do not check `returncode`.
* **Impact:** Corrupted, zero-byte intermediate files propagate down the pipeline, causing cascading failures.
* **Resolution:** Centralized `safe_ffmpeg_run()` helper with `check=True`, stderr capture, and structured error propagation.

### Bug 10: Audio Duration Desynchronization and Lack of Ducking
* **Location:** `generate_audio.py` (L139-149) and `render_video.py` (L72-76)
* **Root Cause:** Sound effects have rigid hardcoded 6-second buffers. BGM is mixed via `[sfx][bgm]amix` without sidechain ducking or loudness normalization.
* **Impact:** Loud sound effects drown out narration; BGM abrupt cuts occur; lack of speech-synchronized volume attenuation.
* **Resolution:** Implement FFmpeg audio filters (`sidechaincompress` or dynamic volume envelopes) and EBU R128 loudness normalization (`loudnorm`).

### Bug 11: Lack of Workspace Isolation and Temporary File Leaks
* **Location:** `render_video.py` (L96, 132)
* **Root Cause:** Hardcoded `/tmp/rendered_clips` and `/tmp/concat_list.txt` without unique session IDs or cleanup hooks.
* **Impact:** File collision across parallel runs; disk bloat on persistent runners.
* **Resolution:** Use `tempfile.TemporaryDirectory` with context managers (`with` blocks) guaranteeing cleanup on both success and exception paths.

### Bug 12: Inadequate Output Quality Inspection
* **Location:** `render_video.py` (L244-247)
* **Root Cause:** Validation only checks `os.path.exists(output)`.
* **Impact:** Corrupted headers, black frames, desynchronized audio, or empty video streams pass as "success".
* **Resolution:** Automated QA Engine (Stage H) that runs `ffprobe` stream validation, checks packet continuity, detects black frames via `blackdetect`, and generates a certified `qc_report.json`.

---

## 3. Architecture Gap Analysis: Documentary Pipeline

| Pipeline Stage | Current Implementation | Required Documentary System |
|---|---|---|
| **A. Topic Research** | Non-existent. Fixed dictionary of 4 topics with 8 keywords each. | Dynamic research engine leveraging Wikipedia, scholarly sources, factual knowledge bases, and structured timeline extraction. |
| **B. Script Writing** | Non-existent. No narration text generated. | Chapter-based documentary scriptwriter with hook, body, narrative arc, and conclusion. |
| **C. Storyboard Generation** | Non-existent. Only a flat list of 8 fixed filenames. | Structured JSON storyboard: scene ID, visual description, search queries, generative prompt, duration, transitions, and audio cues. |
| **D. Visual Retrieval & Generation** | Pexels only (or solid color rectangles). | Multi-provider visual manager: Pexels, Pixabay, Wikimedia Commons, and dynamic AI pan/zoom visual generator. |
| **E. Voiceover & Subtitles** | Non-existent. Pure ASMR sound generator. | Natural AI TTS narration in Hindi and English (edge-tts / offline fallback), auto-generated SRT subtitles. |
| **F. Audio Production** | Procedural tone generator (sine waves, noise). | Thematic BGM scoring, contextual sound effects, smart speech ducking, audio normalization. |
| **G. Video Assembly** | Basic concat filter with no transitions or subtitles. | Full HD (1920x1080) & optional 4K renderer with crossfade transitions, subtitles burning, faststart MP4. |
| **H. Quality Control** | Single `os.path.exists` check. | Comprehensive QA verification: video/audio integrity, duration tolerance, sync check, black frame detection, QC report. |

---

## 4. Modern Modular System Blueprint

```
ai-cloud-video-engine/
├── .github/
│   └── workflows/
│       └── generate_documentary.yml  # Cloud pipeline with multi-language & duration inputs
├── engine/                           # Core Documentary Engine Package
│   ├── __init__.py
│   ├── config.py                     # Centralized settings, limits & validation
│   ├── research.py                   # Stage A: Topic research & fact extraction
│   ├── scriptwriter.py               # Stage B: Narrative script & chapter generation
│   ├── storyboard.py                 # Stage C: Dynamic scene & cue planning
│   ├── assets/                       # Stage D: Visual Asset Management
│   │   ├── __init__.py
│   │   ├── base.py                   # Asset provider abstract interface
│   │   ├── pexels.py                 # Pexels stock video provider
│   │   ├── pixabay.py                # Pixabay media provider
│   │   ├── wikimedia.py              # Wikimedia Commons public media provider
│   │   ├── ai_visuals.py             # Dynamic motion visual generator (Ken Burns)
│   │   └── manager.py                # Multi-tier fallback & consistency manager
│   ├── voice/                        # Stage E: Voiceover & Subtitles
│   │   ├── __init__.py
│   │   ├── tts.py                    # Multi-voice TTS (Hindi & English)
│   │   └── subtitles.py              # SRT generator & timing synchronizer
│   ├── audio/                        # Stage F: Audio Production
│   │   ├── __init__.py
│   │   ├── mixer.py                  # Audio ducking, mixing & volume normalization
│   │   ├── sfx.py                    # Context-aware sound effects
│   │   └── bgm.py                    # Thematic background music library
│   ├── renderer/                     # Stage G: FFmpeg Video Editing
│   │   ├── __init__.py
│   │   ├── ffmpeg_utils.py           # Robust FFmpeg command builder & runner
│   │   └── editor.py                 # Scene assembly, xfade transitions & packaging
│   ├── qc/                           # Stage H: Automated Quality Inspection
│   │   ├── __init__.py
│   │   └── inspector.py              # Stream, sync, duration & frame inspector
│   └── pipeline.py                   # Main Orchestrator (Stages A - H)
├── tests/                            # Comprehensive Automated Test Suite
│   ├── test_config.py
│   ├── test_research.py
│   ├── test_scriptwriter.py
│   ├── test_storyboard.py
│   ├── test_assets.py
│   ├── test_voice.py
│   ├── test_audio.py
│   ├── test_renderer.py
│   ├── test_qc.py
│   └── test_pipeline.py
├── trigger_video.py                  # Hardened, injection-safe mobile trigger CLI
├── requirements.txt                  # Cloud runner dependencies
└── README.md                         # Comprehensive documentation
```
