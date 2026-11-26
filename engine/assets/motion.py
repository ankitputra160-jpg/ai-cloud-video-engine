"""
engine/assets/motion.py - Portrait-Safe 2D Ken Burns Image-to-Video Animator
Frames portrait/square photos cleanly over a blurred backdrop, animates landscape photos
with smooth Ken Burns zoom/pan (1.0x-1.08x) + subtle archival film grain (`noise=alls=4:allf=t`),
and renders date badges via Pillow+raqm PNG or libass (ZERO FFmpeg `drawtext` on Devanagari).
"""
import json
import logging
import os
import subprocess
from typing import Optional, Tuple

from engine.text.devanagari import (
    check_raqm_support,
    get_fonts_dir,
    normalize_devanagari,
    resolve_devanagari_font,
)

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


def _build_badge_ass(badge_text: str, ass_path: str, dur: float, width: int, height: int) -> bool:
    """Write a top-left documentary date/label ASS overlay shaped by libass+HarfBuzz (no drawtext)."""
    if not badge_text:
        return False
    clean = normalize_devanagari(badge_text).replace("{", "").replace("}", "")[:42]
    ass_txt = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: DateBadge,Noto Sans Devanagari Bold,32,&H00FFFFFF,&H00FFFFFF,&H00000000,&HB80F172A,"
        "-1,0,0,0,100,100,0,0,4,12,0,7,48,48,42,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:{min(59.9, dur):05.2f},DateBadge,,0,0,0,,{clean}\n"
    )
    try:
        with open(ass_path, "w", encoding="utf-8-sig") as f:
            f.write(ass_txt)
        return True
    except Exception:
        return False


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
    add_film_grain: bool = True,
) -> Optional[str]:
    """Animate landscape photos with Ken Burns motion + grain; composite portraits over blur."""
    if not image_path or not os.path.exists(image_path):
        return None

    dur = max(1.0, float(duration))
    total_frames = max(25, int(round(dur * fps)))
    img_w, img_h = _probe_image_dims(image_path)
    aspect = (img_w / img_h) if img_h > 0 else 1.77
    is_portrait_or_square = aspect < 1.30

    badge_ass_path = output_path + ".badge.ass"
    badge_vf = ""
    if date_badge and _build_badge_ass(date_badge, badge_ass_path, dur, width, height):
        fonts_dir = os.path.abspath(get_fonts_dir()).replace("\\", "/").replace(":", "\\:")
        esc_ass = os.path.abspath(badge_ass_path).replace("\\", "/").replace(":", "\\:")
        badge_vf = f",ass='{esc_ass}':fontsdir='{fonts_dir}'"

    grain_vf = ",noise=alls=4:allf=t" if add_film_grain else ""

    if is_portrait_or_square:
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
            f"vignette=PI/6:mode=backward{grain_vf}{badge_vf},format=yuv420p[vout]"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-t", f"{dur:.3f}", "-i", image_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    else:
        scale_w = min(3840, width * 2)
        scale_h = min(2160, height * 2)

        if camera == "pull_out":
            z_expr = f"max(1.0,1.08-0.08*(on/{total_frames}))"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif camera == "pan_left":
            z_expr = "1.08"
            x_expr = f"(iw-iw/zoom)*(1-on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif camera == "pan_right":
            z_expr = "1.08"
            x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            z_expr = f"min(1.08,1+0.08*(on/{total_frames}))"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"

        vf = (
            f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={scale_w}:{scale_h},"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={width}x{height}:fps={fps},"
            f"vignette=PI/5:mode=backward{grain_vf}{badge_vf},format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", image_path,
            "-vf", vf,
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if os.path.exists(badge_ass_path):
            os.remove(badge_ass_path)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            return output_path
        logger.warning(f"Image animation error for {image_path}: {res.stderr[-250:]}")
    except Exception as e:
        if os.path.exists(badge_ass_path):
            os.remove(badge_ass_path)
        logger.warning(f"Image animation exception for {image_path}: {e}")
    return None
