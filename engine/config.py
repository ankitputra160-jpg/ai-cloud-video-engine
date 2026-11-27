"""
engine/config.py - Centralized configuration, validation, and profile management
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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
    "fish",
    "sarvam",
    "cartesia",
    "elevenlabs",
    "indicf5",
    "indic_parler",
    "qwen3_tts",
    "piper",
    "edge",
)

SUPPORTED_LLM_MODES: Tuple[str, ...] = (
    "auto",
    "local_gemma3",
    "gemini",
    "groq",
    "deterministic",
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
    },
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

    # v3.0 Modular & Cloud GPU parameters (all optional with clean defaults)
    llm_mode: str = "auto"
    voice_bank_dir: Optional[str] = None
    voice_ref_file: Optional[str] = None
    voice_ref_text: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    bgm_bank_dir: Optional[str] = None
    enable_ai_video: bool = True
    preview_only: bool = False
    generate_thumbnail: bool = True
    thumbnail_path: Optional[str] = None

    # API Keys & Tokens loaded safely from environment (all optional)
    pexels_api_key: Optional[str] = field(default=None)
    pixabay_api_key: Optional[str] = field(default=None)
    nasa_api_key: Optional[str] = field(default=None)
    gemini_api_key: Optional[str] = field(default=None)
    groq_api_key: Optional[str] = field(default=None)
    hf_token: Optional[str] = field(default=None)
    sarvam_api_key: Optional[str] = field(default=None)
    sarvam_speaker: Optional[str] = field(default=None)
    fish_api_key: Optional[str] = field(default=None)
    fish_reference_id: Optional[str] = field(default=None)
    cartesia_api_key: Optional[str] = field(default=None)
    cartesia_voice_id: Optional[str] = field(default=None)
    elevenlabs_api_key: Optional[str] = field(default=None)

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

        self.llm_mode = (self.llm_mode or "auto").lower()
        if self.llm_mode not in SUPPORTED_LLM_MODES:
            self.llm_mode = "auto"

        env_map = (
            ("pexels_api_key", "PEXELS_API_KEY"),
            ("pixabay_api_key", "PIXABAY_API_KEY"),
            ("nasa_api_key", "NASA_API_KEY"),
            ("gemini_api_key", "GEMINI_API_KEY"),
            ("groq_api_key", "GROQ_API_KEY"),
            ("hf_token", "HF_TOKEN"),
            ("sarvam_api_key", "SARVAM_API_KEY"),
            ("sarvam_speaker", "SARVAM_SPEAKER"),
            ("fish_api_key", "FISH_API_KEY"),
            ("fish_reference_id", "FISH_REFERENCE_ID"),
            ("cartesia_api_key", "CARTESIA_API_KEY"),
            ("cartesia_voice_id", "CARTESIA_VOICE_ID"),
            ("elevenlabs_api_key", "ELEVENLABS_API_KEY"),
            ("elevenlabs_voice_id", "ELEVENLABS_VOICE_ID"),
        )
        for attr_name, env_key in env_map:
            if not getattr(self, attr_name, None):
                setattr(self, attr_name, os.environ.get(env_key, "").strip() or None)

        if not self.thumbnail_path:
            base_no_ext = os.path.splitext(self.output_path)[0]
            self.thumbnail_path = f"{base_no_ext}_thumbnail.jpg"

        Path(self.work_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_topic(topic: str) -> str:
        """Strip control characters, excessive whitespace, and dangerous shell metacharacters."""
        if not topic:
            return "General Documentary"
        cleaned = re.sub(r"[\r\n\t]+", " ", topic)
        cleaned = re.sub(r"[^\w\s\-\.,\']", "", cleaned, flags=re.UNICODE)
        cleaned = " ".join(cleaned.split())
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
