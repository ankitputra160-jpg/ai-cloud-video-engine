"""
engine/assets/motion.py - Shared Portrait-Safe 2D Ken Burns Image-to-Video Animator
Automatically detects portrait/square photos and composites them cleanly over a blurred
cinematic backdrop (never slicing heads or leaving ugly black sidebars), while giving landscape
photos smooth Ken Burns pan/zoom motion.
"""
import json
import logging
import os
import subprocess
from typing import Optional, Tuple

from engine.text.devanagari import normalize_devanagari, resolve_devanagari_font

logger = logging.getLogger("assets.motion")


def _probe_image_dims(image_path: str) -> Tuple[int, int]:
    """Read still image dimensions via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        image_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if streams:
            return int(streams[0].get("width", 1920)), int(streams[0].get("height", 1080))
    except Exception:
        pass
    return 1920, 1080


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
    """Animate landscape photos with Ken Burns motion, and frame portrait photos over a blurred backdrop."""
    if not image_path or not os.path.exists(image_path):
        return None

    dur = max(2.0, float(duration))
    total_frames = max(50, int(round(dur * fps)))
    img_w, img_h = _probe_image_dims(image_path)
    aspect = (img_w / img_h) if img_h > 0 else 1.77
    is_portrait_or_square = aspect < 1.30

    overlay_badge_vf = ""
    if date_badge:
        safe_badge = normalize_devanagari(date_badge).replace(":", "\\:").replace("'", "").replace("%", "\\%")[:40]
        font_path = resolve_devanagari_font()
        font_opt = f":fontfile='{font_path}'" if font_path else ""
        overlay_badge_vf = (
            f",drawtext=text='{safe_badge}'{font_opt}:"
            f"fontcolor=white@0.95:fontsize=30:x=56:y=48:"
            f"box=1:boxcolor=black@0.72:boxborderw=12"
        )

    if is_portrait_or_square:
        # Blurred studio backdrop + centered sharp framed portrait with subtle slow scale
        fg_w = int(width * 0.78)
        fg_h = int(height * 0.86)
        filter_complex = (
            f"[0:v]split=2[bg_src][fg_src];"
            f"[bg_src]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=24:4,eq=brightness=-0.18:saturation=0.85[bg];"
            f"[fg_src]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
            f"zoompan=z='min(1.06,1+0.06*(on/{total_frames}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={width}x{height}:fps={fps},"
            f"vignette=PI/6:mode=backward{overlay_badge_vf},format=yuv420p[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(dur), "-i", image_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    else:
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
        else:
            z_expr = f"min(1.18,1+0.18*(on/{total_frames}))"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"

        vf = (
            f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={scale_w}:{scale_h},"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={width}x{height}:fps={fps},"
            f"vignette=PI/5:mode=backward{overlay_badge_vf},format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", image_path,
            "-vf", vf,
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
