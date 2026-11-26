"""
engine/voice - Expressive Narration, Emotion Tag Routing, CTC Forced Alignment & Dual-Layer Subtitles
"""
from engine.voice.aligner import ForcedAligner
from engine.voice.emotion_router import (
    EMOTION_PROFILES,
    apply_prosody_dsp,
    parse_emotion_script,
    stitch_emotional_segments,
)
from engine.voice.subtitles import SubtitleGenerator
from engine.voice.tts import VoiceEngine

__all__ = [
    "VoiceEngine",
    "SubtitleGenerator",
    "ForcedAligner",
    "EMOTION_PROFILES",
    "parse_emotion_script",
    "apply_prosody_dsp",
    "stitch_emotional_segments",
]
