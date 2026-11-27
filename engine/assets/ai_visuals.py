"""
engine/assets/ai_visuals.py - Cinematic & 2D Editorial Motion Card Generator
Generates high-definition 2D editorial motion backdrops (layered grid/gradients, shaped Devanagari
typography via Pillow+raqm or Noto font, subtle vignette, and Ken Burns pan/zoom).
Designed so luminance stays clear of QC black-frame thresholds.
"""
import logging
import os
import subprocess
from typing import Optional

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video
from engine.text.devanagari import (
    check_raqm_support,
    contains_devanagari,
    normalize_devanagari,
    resolve_devanagari_font,
    wrap_indic_text,
)

logger = logging.getLogger("assets.ai_visuals")


class CinematicMotionVisualProvider(VisualAssetProvider):
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 25):
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "cinematic_motion_generator"

    def is_available(self) -> bool:
        return True

    def fetch_video(self, queries: list, target_path: str, min_duration: float = 6.0) -> Optional[str]:
        label = queries[0] if queries else "Historical Archive"
        return self.generate_motion_clip(target_path, label, duration=min_duration)

    def generate_motion_clip(
        self,
        output_path: str,
        title: str,
        duration: float = 6.0,
        mood: str = "epic",
        camera: str = "push_in",
        date_badge: str = "",
    ) -> Optional[str]:
        """Render a rich 2D editorial card (via Pillow+raqm if available) or animated gradient canvas."""
        dur = max(2.0, float(duration))
        clean_title = normalize_devanagari(title) or "Documentary Chapter"

        palettes = {
            "mysterious": ("#1b2a4a", "#2b4162", "#60a5fa"),
            "curious": ("#1b3b36", "#275d52", "#34d399"),
            "intense": ("#4a1c1c", "#7f1d1d", "#f59e0b"),
            "focused": ("#2b2d42", "#4a4e69", "#fbbf24"),
            "inspiring": ("#2e1f47", "#4c2f7a", "#facc15"),
            "epic": ("#1e293b", "#334155", "#f59e0b"),
        }
        c1, c2, accent = palettes.get(mood, palettes["epic"])

        # Preferred path: Pillow + libraqm editorial 2D card animated via Ken Burns
        card_img = output_path + ".card.png"
        if self._render_pillow_2d_card(card_img, clean_title, c1, c2, accent, date_badge):
            anim = animate_image_to_video(
                card_img,
                output_path,
                duration=dur,
                width=self.width,
                height=self.height,
                fps=self.fps,
                camera=camera,
                date_badge="",
            )
            if os.path.exists(card_img):
                os.remove(card_img)
            if anim:
                logger.info(f"2D editorial motion graphic rendered: {output_path}")
                return output_path

        if os.path.exists(card_img):
            os.remove(card_img)

        # Fallback FFmpeg gradient + libass static Devanagari overlay (never drawtext on Hindi!)
        from engine.text.devanagari import format_ass_timestamp, get_fonts_dir
        ass_tmp = output_path + ".title.ass"
        lines_txt = "\\N".join(wrap_indic_text(clean_title, max_graphemes=28, max_lines=3)).replace("{", "").replace("}", "")
        end_ts = format_ass_timestamp(dur)
        ass_body = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
            "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: CardCenter,Noto Sans Devanagari Bold,56,&H00FFFFFF,&H00FFFFFF,&H00000000,&HAA0F172A,"
            "-1,0,0,0,100,100,0,0,4,18,0,5,100,100,40,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,{end_ts},CardCenter,,0,0,0,,{lines_txt}\n"
        )
        with open(ass_tmp, "w", encoding="utf-8-sig") as f:
            f.write(ass_body)
        esc_ass = os.path.abspath(ass_tmp).replace("\\", "/").replace(":", "\\:")
        esc_fonts = os.path.abspath(get_fonts_dir()).replace("\\", "/").replace(":", "\\:")

        filter_script = (
            f"format=yuv420p,"
            f"geq="
            f"r='50 + (X/{self.width})*70 + 20*sin(2*PI*(T/{dur}))':"
            f"g='45 + (Y/{self.height})*55 + 20*cos(2*PI*(T/{dur}))':"
            f"b='80 + 30*sin(2*PI*(T/{dur} + X/{self.width}))',"
            f"vignette=PI/6:mode=backward,noise=alls=4:allf=t,"
            f"ass='{esc_ass}':fontsdir='{esc_fonts}'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={c1}:s={self.width}x{self.height}:r={self.fps}:d={dur}",
            "-vf", filter_script,
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if os.path.exists(ass_tmp):
                os.remove(ass_tmp)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                logger.info(f"Cinematic motion graphic rendered: {output_path}")
                return output_path
            logger.warning(f"FFmpeg motion visual error: {res.stderr[-300:]}")
            return self._fallback_simple_motion(output_path, dur, c2)
        except Exception as e:
            if os.path.exists(ass_tmp):
                os.remove(ass_tmp)
            logger.error(f"Failed to generate motion visual: {e}")
            return self._fallback_simple_motion(output_path, dur, c2)

    def _render_pillow_2d_card(
        self, img_path: str, title: str, bg_hex: str, card_hex: str, accent_hex: str, date_badge: str
    ) -> bool:
        """Render a crisp 2D layered vector-like frame using Pillow + libraqm (when available)."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return False

        try:
            img = Image.new("RGB", (self.width, self.height), bg_hex)
            draw = ImageDraw.Draw(img)

            # Subtle editorial blueprint grid lines
            step = max(60, self.width // 24)
            for gx in range(0, self.width, step):
                draw.line([(gx, 0), (gx, self.height)], fill=card_hex, width=1)
            for gy in range(0, self.height, step):
                draw.line([(0, gy), (self.width, gy)], fill=card_hex, width=1)

            # Center framed documentary card
            pad_x = int(self.width * 0.12)
            pad_y = int(self.height * 0.22)
            draw.rounded_rectangle(
                [pad_x, pad_y, self.width - pad_x, self.height - pad_y],
                radius=24,
                fill=card_hex,
                outline=accent_hex,
                width=4,
            )

            # Accent top bar inside card
            draw.rectangle([pad_x + 48, pad_y + 42, pad_x + 180, pad_y + 50], fill=accent_hex)

            font_path = resolve_devanagari_font("Baloo2-Bold.ttf") or resolve_devanagari_font("Khand-Bold.ttf")
            use_raqm = check_raqm_support()
            font_size = max(36, int(self.height * 0.052))

            if font_path:
                kwargs = {"layout_engine": ImageFont.Layout.RAQM} if use_raqm else {}
                font = ImageFont.truetype(font_path, font_size, **kwargs)
                badge_font = ImageFont.truetype(font_path, max(24, font_size // 2), **kwargs)
            else:
                font = ImageFont.load_default()
                badge_font = font

            if date_badge:
                draw.text((pad_x + 48, pad_y + 70), normalize_devanagari(date_badge), fill=accent_hex, font=badge_font)

            lines = wrap_indic_text(title, max_graphemes=28, max_lines=3)[:3]
            text_y = pad_y + int((self.height - 2 * pad_y) * 0.36)
            for ln in lines:
                draw.text((pad_x + 48, text_y), ln, fill="#F8FAFC", font=font)
                text_y += int(font_size * 1.45)

            img.save(img_path, "PNG")
            return os.path.exists(img_path)
        except Exception as e:
            logger.debug(f"Pillow 2D card render fallback: {e}")
            return False

    def _fallback_simple_motion(self, output_path: str, duration: float, color: str) -> Optional[str]:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={color}:s={self.width}x{self.height}:r={self.fps}:d={duration}",
            "-vf", "vignette=PI/6",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and os.path.exists(output_path):
            return output_path
        return None

    def _escape_text(self, text: str) -> str:
        return text.replace(":", "\\:").replace("'", "").replace("%", "\\%")[:60]
