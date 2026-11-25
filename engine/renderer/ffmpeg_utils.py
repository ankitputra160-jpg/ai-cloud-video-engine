"""
engine/renderer/ffmpeg_utils.py - Safe FFmpeg Command Execution & Probe Utilities
"""
import subprocess
import logging
import json
from typing import Dict, Any, Optional

logger = logging.getLogger("renderer.ffmpeg")

def safe_run_ffmpeg(cmd: list, label: str = "FFmpeg Task", timeout: int = 300) -> bool:
    """Executes FFmpeg with strict returncode checking and diagnostic error capture."""
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
    """Inspects media file via ffprobe and returns container and stream properties."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        filepath
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception as e:
        logger.warning(f"ffprobe failed for {filepath}: {e}")
    return {}

def get_duration(filepath: str) -> float:
    """Returns media duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(res.stdout.strip())
    except Exception:
        return 0.0
