"""
engine/renderer/ffmpeg_utils.py - Safe FFmpeg Execution, Hardware NVENC Auto-Detect & Probing
"""
import json
import logging
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger("renderer.ffmpeg")
_CACHED_ENCODER: Optional[str] = None


def detect_h264_encoder(force_cpu: bool = False) -> str:
    """Probe whether FFmpeg supports hardware `h264_nvenc` on Colab GPU, else return `libx264`."""
    global _CACHED_ENCODER
    if force_cpu:
        return "libx264"
    if _CACHED_ENCODER is not None:
        return _CACHED_ENCODER

    try:
        enc_list = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=6)
        if "h264_nvenc" in (enc_list.stdout or ""):
            probe_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ]
            res = subprocess.run(probe_cmd, capture_output=True, timeout=8)
            if res.returncode == 0:
                _CACHED_ENCODER = "h264_nvenc"
                logger.info("Detected working GPU hardware encoder: h264_nvenc")
                return _CACHED_ENCODER
    except Exception:
        pass

    _CACHED_ENCODER = "libx264"
    return _CACHED_ENCODER


def safe_run_ffmpeg(cmd: list, label: str = "FFmpeg Task", timeout: int = 300) -> bool:
    """Execute FFmpeg with strict returncode checking and diagnostic error capture."""
    logger.debug(f"Starting {label}: {' '.join(cmd[:6])}...")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            logger.error(f"❌ {label} failed with exit code {res.returncode}:\n{res.stderr[-400:]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"❌ {label} timed out after {timeout} seconds")
        return False
    except Exception as e:
        logger.error(f"❌ {label} unexpected execution error: {e}")
        return False


def get_media_info(filepath: str) -> Dict[str, Any]:
    """Inspect media file via ffprobe and returns container and stream properties."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        filepath,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception as e:
        logger.warning(f"ffprobe failed for {filepath}: {e}")
    return {}


def get_duration(filepath: str) -> float:
    """Return exact media duration in seconds (0.001s resolution)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(res.stdout.strip())
    except Exception:
        return 0.0
