"""
engine/config.py - Centralized configuration, validation, and profile management
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

MAX_DURATION_SECONDS = 1500  # 25 minutes max runtime
MIN_DURATION_SECONDS = 10

SUPPORTED_STYLES: Tuple[str, ...] = (
    "Documentary",
    "2D Animation",
    "Vox Explainer",
    "Historical",
    "Scientific",
    "Biographical",
)

SUPPORTED_SUBTITLE_STYLES: Tuple[str, ...] = (
    "ass_karaoke",
    "pill_box",
    "srt_classic",
)

SUPPORTED_VOICE_ENGINES: Tuple[str, ...] = (
    "auto",
    "piper",
    "edge",
)

@dataclass
class ResolutionProfile:
    name: str
    width: int
    height: int
    video_bitrate: str
    crf: int
    fps: int = 25

PROFILES: Dict[str, ResolutionProfile] = {
    "1080p": ResolutionProfile(name="1080p", width=1920, height=1080, video_bitrate="6M", crf=22, fps=25),
    "4k": ResolutionProfile(name="4k", width=3840, height=2160, video_bitrate="20M", crf=20, fps=25),
    "720p": ResolutionProfile(name="720p", width=1280, height=720, video_bitrate="3M", crf=24, fps=25),
}

VOICE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "en": {
        "primary": "en-US-ChristopherNeural",
        "secondary": "en-US-EricNeural",
        "female": "en-US-AriaNeural",
        "words_per_minute": 140,
        "piper_model": "en_US-lessac-medium",
        "piper_onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "piper_json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    },
    "hi": {
        "primary": "hi-IN-MadhurNeural",
        "secondary": "hi-IN-SwaraNeural",
        "female": "hi-IN-SwaraNeural",
        "words_per_minute": 125,
        "piper_model": "hi_IN-rohan-medium",
        "piper_onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/rohan/medium/hi_IN-rohan-medium.onnx",
        "piper_json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/rohan/medium/hi_IN-rohan-medium.onnx.json",
    }
}

@dataclass
class PipelineConfig:
    topic: str
    style: str = "Documentary"
    duration: int = 60
    language: str = "en"
    resolution: str = "1080p"
    output_path: str = "output/documentary.mp4"
    work_dir: str = ".workspace"
    enable_qc: bool = True
    burn_subtitles: bool = True
    subtitle_style: str = "ass_karaoke"
    voice_engine: str = "auto"
    storyboard_file: Optional[str] = None

    # API Keys loaded safely from environment (all optional for free-tier execution)
    pexels_api_key: Optional[str] = field(default=None)
    pixabay_api_key: Optional[str] = field(default=None)
    nasa_api_key: Optional[str] = field(default=None)
    gemini_api_key: Optional[str] = field(default=None)
    groq_api_key: Optional[str] = field(default=None)

    # Network & Retry limits
    http_timeout: int = 15
    max_retries: int = 3

    def __post_init__(self):
        self.topic = self.sanitize_topic(self.topic)

        if self.duration < MIN_DURATION_SECONDS:
            self.duration = MIN_DURATION_SECONDS
        elif self.duration > MAX_DURATION_SECONDS:
            self.duration = MAX_DURATION_SECONDS

        self.language = self.language.lower()
        if self.language not in ("en", "hi"):
            self.language = "en"

        self.resolution = self.resolution.lower()
        if self.resolution not in PROFILES:
            self.resolution = "1080p"

        if self.subtitle_style not in SUPPORTED_SUBTITLE_STYLES:
            self.subtitle_style = "ass_karaoke"

        self.voice_engine = self.voice_engine.lower()
        if self.voice_engine not in SUPPORTED_VOICE_ENGINES:
            self.voice_engine = "auto"

        if not self.pexels_api_key:
            self.pexels_api_key = os.environ.get("PEXELS_API_KEY", "").strip() or None
        if not self.pixabay_api_key:
            self.pixabay_api_key = os.environ.get("PIXABAY_API_KEY", "").strip() or None
        if not self.nasa_api_key:
            self.nasa_api_key = os.environ.get("NASA_API_KEY", "").strip() or None
        if not self.gemini_api_key:
            self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip() or None
        if not self.groq_api_key:
            self.groq_api_key = os.environ.get("GROQ_API_KEY", "").strip() or None

        Path(self.work_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_topic(topic: str) -> str:
        """Strip control characters, excessive whitespace, and dangerous shell metacharacters."""
        if not topic:
            return "General Documentary"
        cleaned = re.sub(r'[\r\n\t]+', ' ', topic)
        cleaned = re.sub(r'[^\w\s\-\.,\']', '', cleaned, flags=re.UNICODE)
        cleaned = ' '.join(cleaned.split())
        return cleaned[:150].strip() or "General Documentary"

    @property
    def is_2d_style(self) -> bool:
        """Return True when 2D Animation or Vox Explainer production mode is active."""
        s = self.style.lower()
        return "2d" in s or "vox" in s or "explainer" in s

    @property
    def profile(self) -> ResolutionProfile:
        return PROFILES[self.resolution]

    @property
    def voice_settings(self) -> Dict[str, Any]:
        return VOICE_CONFIGS.get(self.language, VOICE_CONFIGS["en"])
