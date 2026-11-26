"""
engine/renderer - Video Assembly, NVENC Hardware Acceleration, Auto-Thumbnail & FFmpeg Utilities
"""
from engine.renderer.editor import VideoEditor
from engine.renderer.ffmpeg_utils import (
    detect_h264_encoder,
    get_duration,
    get_media_info,
    safe_run_ffmpeg,
)
from engine.renderer.thumbnail import AutoThumbnailGenerator

__all__ = [
    "safe_run_ffmpeg",
    "get_media_info",
    "get_duration",
    "detect_h264_encoder",
    "VideoEditor",
    "AutoThumbnailGenerator",
]
