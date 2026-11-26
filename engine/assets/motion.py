"""
engine/assets/motion.py - Shared 2D Ken Burns Image-to-Video Motion Animator
Converts high-resolution historical photos, NASA imagery, and AI 2D illustrations into smooth,
broadcast-grade animated MP4 video clips without duplicating FFmpeg filtergraph logic.
"""
import logging
import os
import subprocess
from typing import Optional

from engine.text.devanagari import resolve_devanagari_font

logger = logging.getLogger("assets.motion")


def animate_image_to_video(
    image_path: str,
    output_path: str,
    duration: float = 10.0,
    width: int = 1920,
    height: int = 1080,
    fps: int = 25,
    camera: str = "push_in",
    date_badge: str = "",
    timeout: int = 90,
) -> Optional[str]:
    """Animate a still image using smooth FFmpeg Ken Burns zoom/pan and optional date stamp."""
    if not image_path or not os.path.exists(image_path):
        return None

    dur = max(2.0, float(duration))
    total_frames = max(50, int(round(dur * fps)))

    # Scale image oversized first so zoompan stays sharp with zero jitter
    scale_w = min(3840, width * 2)
    scale_h = min(2160, height * 2)

    if camera == "pull_out":
        z_expr = f"max(1.0,1.16-0.16*(on/{total_frames}))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "pan_left":
        z_expr = "1.14"
        x_expr = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif camera == "pan_right":
        z_expr = "1.14"
        x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:  # push_in / drift default
        z_expr = f"min(1.18,1+0.18*(on/{total_frames}))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    vf_parts = [
        f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase",
        f"crop={scale_w}:{scale_h}",
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={width}x{height}:fps={fps}",
        "vignette=PI/5:mode=backward",
        "format=yuv420p",
    ]

    if date_badge:
        safe_badge = date_badge.replace(":", "\\:").replace("'", "").replace("%", "\\%")[:32]
        font_path = resolve_devanagari_font()
        font_opt = f":fontfile='{font_path}'" if font_path else ""
        vf_parts.append(
            f"drawtext=text='{safe_badge}'{font_opt}:"
            f"fontcolor=white@0.95:fontsize=30:x=56:y=48:"
            f"box=1:boxcolor=black@0.65:boxborderw=12"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", image_path,
        "-vf", ",".join(vf_parts),
        "-t", str(dur),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            return output_path
        logger.warning(f"Image animation error for {image_path}: {res.stderr[-250:]}")
    except Exception as e:
        logger.warning(f"Image animation exception for {image_path}: {e}")
    return None
