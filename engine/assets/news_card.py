"""
engine/assets/news_card.py - Programmatic Investigative News Cutting, Quote, Map & Stat Cards
Renders watermark-free Dhruv Rathee style editorial visuals via:
  1. Playwright (Headless Chromium) HTML/CSS/SVG -> guaranteed HarfBuzz Hindi shaping + animated
     yellow marker highlight sweep (`clip-path: inset(0 100% 0 0)` -> `0%`) & MapLibre/SVG pin
  2. Pillow + libraqm static Devanagari fallback (when headless Chromium not present)
  3. FFmpeg ASS overlay + Ken Burns fallback (zero FFmpeg `drawtext` on Hindi script)
"""
import html as _html
import logging
import os
import subprocess
import tempfile
from typing import Optional

from engine.assets.motion import animate_image_to_video
from engine.text.devanagari import (
    check_raqm_support,
    contains_devanagari,
    get_fonts_dir,
    normalize_devanagari,
    resolve_devanagari_font,
    wrap_indic_text,
)

logger = logging.getLogger("assets.news_card")


def _font_file_uri(filename: str) -> str:
    fonts_dir = get_fonts_dir()
    p = os.path.join(fonts_dir, filename)
    if os.path.exists(p):
        return f"file://{os.path.abspath(p)}"
    resolved = resolve_devanagari_font()
    return f"file://{os.path.abspath(resolved)}" if resolved else ""


class InvestigativeCardGenerator:
    """Renders 2D investigative cards: news_card, quote_card, map_card, stat_card."""

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 25):
        self.width = width
        self.height = height
        self.fps = fps

    def _has_playwright(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except ImportError:
            return False

    def render_card_video(
        self,
        output_path: str,
        card_type: str = "news_card",
        headline: str = "",
        source: str = "Investigative Desk",
        date_badge: str = "",
        duration: float = 4.0,
        camera: str = "push_in",
        portrait_path: Optional[str] = None,
    ) -> Optional[str]:
        """Create a dynamic 2D editorial MP4 clip (no watermark, intact Hindi matras)."""
        dur = max(1.5, float(duration))
        clean_head = normalize_devanagari(headline) or "Documentary Report"
        clean_src = normalize_devanagari(source) or "Public Record"
        clean_date = normalize_devanagari(date_badge)

        if self._has_playwright():
            pw_res = self._render_via_playwright(
                output_path, card_type, clean_head, clean_src, clean_date, dur, camera, portrait_path
            )
            if pw_res:
                return pw_res

        # High-craft Pillow + libraqm fallback (animate to MP4)
        png_tmp = output_path + ".card.png"
        if self._render_via_pillow(png_tmp, card_type, clean_head, clean_src, clean_date):
            ok = animate_image_to_video(
                png_tmp,
                output_path,
                duration=dur,
                width=self.width,
                height=self.height,
                fps=self.fps,
                camera=camera,
                date_badge="",
                add_film_grain=True,
            )
            if os.path.exists(png_tmp):
                os.remove(png_tmp)
            if ok:
                return output_path
        if os.path.exists(png_tmp):
            os.remove(png_tmp)

        # Pure FFmpeg + libass fallback (guarantees Hindi shaping even without Pillow or Chromium)
        return self._render_via_ffmpeg_ass(output_path, card_type, clean_head, clean_src, clean_date, dur)

    def _build_html_document(
        self, card_type: str, headline: str, source: str, date_badge: str, portrait_b64: str = ""
    ) -> str:
        bold_uri = _font_file_uri("NotoSansDevanagari-Bold.ttf")
        reg_uri = _font_file_uri("NotoSansDevanagari-Regular.ttf")
        esc_h = _html.escape(headline)
        esc_s = _html.escape(source)
        esc_d = _html.escape(date_badge)

        font_css = f"""
        @font-face {{ font-family: 'NotoDeva'; src: url('{reg_uri}'); font-weight: 400; }}
        @font-face {{ font-family: 'NotoDeva'; src: url('{bold_uri}'); font-weight: 700; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            width: {self.width}px; height: {self.height}px; overflow: hidden;
            font-family: 'NotoDeva', 'Noto Sans Devanagari', sans-serif;
            display: flex; align-items: center; justify-content: center;
        }}
        """

        if card_type == "news_card":
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
            body {{ background: radial-gradient(circle at 30% 20%, #1e293b 0%, #090d16 100%); }}
            .paper {{
                width: 78%; padding: 64px 72px; background: #f8f5ec; color: #111827;
                border-radius: 12px; box-shadow: 0 32px 80px rgba(0,0,0,0.65);
                border-top: 12px solid #b91c1c; position: relative;
            }}
            .meta {{ display: flex; justify-content: space-between; font-size: 26px; font-weight: 700;
                color: #b91c1c; border-bottom: 2px solid #d6d3c9; padding-bottom: 18px; margin-bottom: 34px; text-transform: uppercase; }}
            .headline {{ font-size: 56px; line-height: 1.42; font-weight: 700; color: #0f172a; }}
            .highlight {{
                background: linear-gradient(104deg, rgba(250,204,21,0) 0.9%, rgba(250,204,21,0.88) 2.4%, rgba(250,204,21,0.82) 96%, rgba(250,204,21,0) 99%);
                padding: 4px 10px; border-radius: 6px;
                animation: sweep 1.1s ease-out forwards;
            }}
            @keyframes sweep {{ from {{ clip-path: inset(0 100% 0 0); }} to {{ clip-path: inset(0 0 0 0); }} }}
            </style></head><body>
            <div class="paper">
              <div class="meta"><span>{esc_s}</span><span>{esc_d or 'VERIFIED RECORD'}</span></div>
              <div class="headline"><span class="highlight">{esc_h}</span></div>
            </div></body></html>"""

        if card_type == "quote_card":
            avatar_html = f'<img src="data:image/png;base64,{portrait_b64}" class="avatar"/>' if portrait_b64 else ""
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
            body {{ background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); color: #f8fafc; }}
            .box {{ width: 80%; padding: 68px; border-left: 14px solid #f59e0b; background: rgba(15,23,42,0.85);
                border-radius: 16px; display: flex; gap: 48px; align-items: center; box-shadow: 0 28px 70px rgba(0,0,0,0.6); }}
            .avatar {{ width: 260px; height: 260px; border-radius: 16px; object-fit: cover; border: 4px solid #f59e0b; }}
            .qmark {{ font-size: 96px; color: #f59e0b; line-height: 0.6; margin-bottom: 18px; }}
            .quote {{ font-size: 50px; line-height: 1.45; font-weight: 700; }}
            .src {{ margin-top: 28px; font-size: 28px; color: #cbd5e1; }}
            </style></head><body><div class="box">{avatar_html}
            <div><div class="qmark">“</div><div class="quote">{esc_h}</div><div class="src">— {esc_s} {('• ' + esc_d) if esc_d else ''}</div></div>
            </div></body></html>"""

        if card_type == "map_card":
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
            body {{ background: #091526; color: #f8fafc; position: relative; }}
            svg {{ width: 92%; height: 84%; }}
            .label {{ position: absolute; bottom: 88px; left: 96px; background: rgba(15,23,42,0.92);
                border-left: 8px solid #ef4444; padding: 24px 36px; border-radius: 10px; font-size: 42px; font-weight: 700; }}
            </style></head><body>
            <svg viewBox="0 0 1200 650">
              <defs><pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e3a5f" stroke-width="1"/></pattern></defs>
              <rect width="1200" height="650" fill="url(#g)"/>
              <path d="M510,95 L590,110 L655,190 L705,230 L680,320 L620,440 L575,555 L540,460 L470,350 L435,245 Z"
                    fill="#1d4ed8" fill-opacity="0.35" stroke="#60a5fa" stroke-width="4"/>
              <circle cx="555" cy="215" r="28" fill="none" stroke="#ef4444" stroke-width="5" opacity="0.75"/>
              <circle cx="555" cy="215" r="11" fill="#ef4444"/>
            </svg>
            <div class="label">{esc_h} {('(' + esc_d + ')') if esc_d else ''}</div></body></html>"""

        # Default: bold stat_card
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
        body {{ background: linear-gradient(145deg, #111827 0%, #1f2937 100%); color: #f9fafb; }}
        .stat {{ width: 78%; padding: 72px; border: 3px solid #f59e0b; border-radius: 24px; text-align: center;
            background: rgba(17,24,39,0.9); box-shadow: 0 30px 75px rgba(0,0,0,0.65); }}
        .badge {{ display: inline-block; background: #f59e0b; color: #111827; font-weight: 700; font-size: 28px;
            padding: 10px 28px; border-radius: 999px; margin-bottom: 32px; }}
        .val {{ font-size: 62px; line-height: 1.38; font-weight: 700; }}
        </style></head><body><div class="stat">
        <div class="badge">{esc_d or esc_s}</div><div class="val">{esc_h}</div>
        </div></body></html>"""

    def _render_via_playwright(
        self,
        output_path: str,
        card_type: str,
        headline: str,
        source: str,
        date_badge: str,
        duration: float,
        camera: str,
        portrait_path: Optional[str],
    ) -> Optional[str]:
        import base64
        portrait_b64 = ""
        if portrait_path and os.path.exists(portrait_path):
            try:
                img_bytes = open(portrait_path, "rb").read()
                try:
                    from rembg import remove
                    img_bytes = remove(img_bytes)
                except Exception:
                    pass
                portrait_b64 = base64.b64encode(img_bytes).decode("ascii")
            except Exception:
                pass

        html_doc = self._build_html_document(card_type, headline, source, date_badge, portrait_b64)
        png_tmp = output_path + ".pw.png"
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": self.width, "height": self.height})
                page.set_content(html_doc, wait_until="load")
                page.wait_for_timeout(1200)  # Let yellow highlighter sweep complete cleanly
                page.screenshot(path=png_tmp)
                browser.close()
            if os.path.exists(png_tmp) and os.path.getsize(png_tmp) > 5000:
                ok = animate_image_to_video(
                    png_tmp, output_path, duration=duration, width=self.width, height=self.height,
                    fps=self.fps, camera=camera, add_film_grain=True,
                )
                os.remove(png_tmp)
                if ok:
                    return output_path
        except Exception as e:
            logger.debug(f"Playwright card render skipped: {e}")
        if os.path.exists(png_tmp):
            os.remove(png_tmp)
        return None

    def _render_via_pillow(
        self, png_path: str, card_type: str, headline: str, source: str, date_badge: str
    ) -> bool:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return False

        try:
            is_news = card_type == "news_card"
            bg = "#0f172a"
            card_bg = "#f8f5ec" if is_news else "#1e293b"
            fg = "#111827" if is_news else "#f8fafc"
            accent = "#b91c1c" if is_news else "#f59e0b"

            img = Image.new("RGB", (self.width, self.height), bg)
            draw = ImageDraw.Draw(img)
            px, py = int(self.width * 0.11), int(self.height * 0.18)
            draw.rounded_rectangle([px, py, self.width - px, self.height - py], radius=20, fill=card_bg, outline=accent, width=6)

            # Use dual-script TTF (Baloo2-Bold / Khand-Bold cover BOTH Latin A-Z and Devanagari + ₹!)
            font_path = resolve_devanagari_font("Baloo2-Bold.ttf") or resolve_devanagari_font("Khand-Bold.ttf")
            use_raqm = check_raqm_support()
            kw = {"layout_engine": ImageFont.Layout.RAQM} if use_raqm else {}
            title_f = ImageFont.truetype(font_path, max(38, self.height // 19), **kw) if font_path else ImageFont.load_default()
            meta_f = ImageFont.truetype(font_path, max(24, self.height // 36), **kw) if font_path else ImageFont.load_default()

            header_txt = f"{source}   |   {date_badge or 'RECORD'}"
            draw.text((px + 56, py + 44), header_txt, font=meta_f, fill=accent)

            lines = wrap_indic_text(headline, max_graphemes=32, max_lines=3)
            y_cur = py + 140
            for ln in lines:
                if is_news:
                    bbox = draw.textbbox((px + 56, y_cur), ln, font=title_f)
                    draw.rectangle([bbox[0] - 8, bbox[1] - 4, bbox[2] + 8, bbox[3] + 6], fill="#fde047")
                draw.text((px + 56, y_cur), ln, font=title_f, fill=fg)
                y_cur += int(self.height * 0.085)

            img.save(png_path)
            return os.path.exists(png_path)
        except Exception as e:
            logger.debug(f"Pillow card render fallback failed: {e}")
            return False

    def _render_via_ffmpeg_ass(
        self, output_path: str, card_type: str, headline: str, source: str, date_badge: str, dur: float
    ) -> Optional[str]:
        """Devanagari-safe card rendered with libass + Static NotoSansDevanagari (never drawtext)."""
        ass_tmp = output_path + ".card.ass"
        lines = wrap_indic_text(headline, max_graphemes=30, max_lines=3)
        body = "\\N".join(lines).replace("{", "").replace("}", "")
        header = f"{source} • {date_badge}" if date_badge else source
        border_col = "&H001C1CB9" if card_type == "news_card" else "&H000B9EF5"

        ass_content = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: CardMain,Noto Sans Devanagari Bold,58,&H00FFFFFF,&H00FFFFFF,{border_col},&HE61E293B,-1,0,0,0,100,100,0,0,4,24,0,5,120,120,40,1\n"
            "Style: CardMeta,Noto Sans Devanagari Bold,32,&H000BD7FA,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,8,80,80,140,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,0:00:{dur:05.2f},CardMeta,,0,0,0,,{header}\n"
            f"Dialogue: 0,0:00:00.00,0:00:{dur:05.2f},CardMain,,0,0,0,,{body}\n"
        )
        with open(ass_tmp, "w", encoding="utf-8-sig") as f:
            f.write(ass_content)

        fonts_dir = os.path.abspath(get_fonts_dir()).replace("\\", "/").replace(":", "\\:")
        esc_ass = os.path.abspath(ass_tmp).replace("\\", "/").replace(":", "\\:")
        vf = f"ass='{esc_ass}':fontsdir='{fonts_dir}',noise=alls=4:allf=t,format=yuv420p"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=#1b2a4a:s={self.width}x{self.height}:r={self.fps}:d={dur:.3f}",
            "-vf", vf,
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        if os.path.exists(ass_tmp):
            os.remove(ass_tmp)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path
        return None
