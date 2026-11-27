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
    format_ass_timestamp,
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
        if self._render_via_pillow(png_tmp, card_type, clean_head, clean_src, clean_date, portrait_path=portrait_path):
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
        baloo_uri = _font_file_uri("Baloo2-Bold.ttf")
        khand_uri = _font_file_uri("Khand-Bold.ttf")
        esc_h = _html.escape(headline)
        esc_s = _html.escape(source)
        esc_d = _html.escape(date_badge)

        font_css = f"""
        @font-face {{ font-family: 'NotoDeva'; src: url('{reg_uri}'); font-weight: 400; }}
        @font-face {{ font-family: 'NotoDeva'; src: url('{bold_uri}'); font-weight: 700; }}
        @font-face {{ font-family: 'BalooDual'; src: url('{baloo_uri}'); font-weight: 700; }}
        @font-face {{ font-family: 'KhandDual'; src: url('{khand_uri}'); font-weight: 700; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            width: {self.width}px; height: {self.height}px; overflow: hidden;
            font-family: 'NotoDeva', 'BalooDual', 'KhandDual', 'Noto Sans Devanagari', sans-serif;
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
            .headline {{ font-size: 56px; line-height: 1.48; font-weight: 700; color: #0f172a; }}
            .highlight {{
                background-image: linear-gradient(104deg, rgba(250,204,21,0) 0.8%, rgba(250,204,21,0.90) 2.5%, rgba(250,204,21,0.85) 96%, rgba(250,204,21,0) 99%);
                background-repeat: no-repeat;
                background-position: 0 72%;
                background-size: var(--sweep-pct, 100%) 76%;
                -webkit-box-decoration-break: clone;
                box-decoration-break: clone;
                padding: 4px 10px; border-radius: 6px;
                animation: sweep 1.15s cubic-bezier(0.22, 1, 0.36, 1) forwards;
            }}
            @keyframes sweep {{ from {{ background-size: 0% 76%; }} to {{ background-size: 100% 76%; }} }}
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

        if card_type == "phone_call_card":
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
            body {{ background: radial-gradient(circle at 50% 40%, #1e1b4b 0%, #050811 100%); color: #f8fafc; }}
            .phone {{
                width: 470px; height: 860px; border-radius: 46px; background: #0b1220;
                border: 6px solid #334155; box-shadow: 0 36px 90px rgba(0,0,0,0.85);
                padding: 52px 34px; display: flex; flex-direction: column; justify-content: space-between; align-items: center;
                position: relative;
            }}
            .top {{ text-align: center; }}
            .tag {{ display: inline-block; background: #dc2626; color: #fff; font-size: 20px; font-weight: 700;
                padding: 8px 20px; border-radius: 999px; letter-spacing: 1px; margin-bottom: 24px; }}
            .caller {{ font-size: 42px; font-weight: 700; line-height: 1.3; margin-bottom: 12px; }}
            .sub {{ font-size: 24px; color: #94a3b8; }}
            .ring-wrap {{ position: relative; width: 220px; height: 220px; display: flex; align-items: center; justify-content: center; }}
            .pulse-ring {{
                position: absolute; width: 170px; height: 170px; border-radius: 50%;
                border: 4px solid rgba(239, 68, 68, 0.7);
                transform: scale(calc(1 + var(--pulse, 0) * 0.45));
                opacity: calc(1 - var(--pulse, 0) * 0.85);
            }}
            .avatar-circle {{
                width: 150px; height: 150px; border-radius: 50%; background: linear-gradient(135deg, #1d4ed8, #b91c1c);
                display: flex; align-items: center; justify-content: center; font-size: 46px; font-weight: 700;
                border: 4px solid #f8fafc; z-index: 2;
            }}
            .actions {{ display: flex; gap: 68px; margin-bottom: 18px; }}
            .btn {{ width: 92px; height: 92px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                font-size: 22px; font-weight: 700; color: #fff; }}
            .decline {{ background: #dc2626; }}
            .accept {{ background: #16a34a; transform: scale(calc(1 + (1 - var(--pulse, 0)) * 0.08)); }}
            </style></head><body><div class="phone">
              <div class="top">
                <div class="tag">{esc_d or 'INCOMING VIDEO CALL'}</div>
                <div class="caller">{esc_h}</div>
                <div class="sub">{esc_s}</div>
              </div>
              <div class="ring-wrap">
                <div class="pulse-ring"></div>
                <div class="avatar-circle">CBI</div>
              </div>
              <div class="actions">
                <div class="btn decline">CUT</div>
                <div class="btn accept">VIDEO</div>
              </div>
            </div></body></html>"""

        if card_type == "waveform_card":
            bars = "".join(
                f'<div class="bar" style="--i:{i}; height: calc(28px + 130px * abs(sin(var(--phase, 0.5) * 6.283 + {i * 0.45:.2f})));"></div>'
                for i in range(28)
            )
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
            body {{ background: radial-gradient(circle at 50% 35%, #172554 0%, #060913 100%); color: #f8fafc; }}
            .panel {{ width: 82%; padding: 62px 68px; border-radius: 24px; background: rgba(15,23,42,0.92);
                border: 3px solid #38bdf8; box-shadow: 0 32px 80px rgba(0,0,0,0.75); text-align: center; }}
            .badge {{ display: inline-block; background: #0284c7; color: #fff; font-size: 24px; font-weight: 700;
                padding: 10px 26px; border-radius: 999px; margin-bottom: 24px; }}
            .title {{ font-size: 52px; font-weight: 700; line-height: 1.38; margin-bottom: 42px; color: #f8fafc; }}
            .wave {{ height: 190px; display: flex; align-items: center; justify-content: center; gap: 14px; }}
            .bar {{ width: 16px; border-radius: 999px; background: linear-gradient(180deg, #38bdf8, #f59e0b);
                min-height: 24px; transition: none; }}
            .src {{ margin-top: 28px; font-size: 26px; color: #94a3b8; }}
            </style></head><body><div class="panel">
              <div class="badge">{esc_d or 'AI VOICE CLONING'}</div>
              <div class="title">{esc_h}</div>
              <div class="wave">{bars}</div>
              <div class="src">{esc_s}</div>
            </div></body></html>"""

        if card_type == "map_card":
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
            body {{ background: #091526; color: #f8fafc; position: relative; }}
            svg {{ width: 92%; height: 84%; }}
            .radar {{ transform-origin: 555px 215px; transform: scale(calc(0.8 + var(--pulse, 0.3) * 1.1)); opacity: calc(1 - var(--pulse, 0.3) * 0.75); }}
            .label {{ position: absolute; bottom: 88px; left: 96px; background: rgba(15,23,42,0.92);
                border-left: 8px solid #ef4444; padding: 24px 36px; border-radius: 10px; font-size: 42px; font-weight: 700; }}
            </style></head><body>
            <svg viewBox="0 0 1200 650">
              <defs><pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e3a5f" stroke-width="1"/></pattern></defs>
              <rect width="1200" height="650" fill="url(#g)"/>
              <path d="M510,95 L590,110 L655,190 L705,230 L680,320 L620,440 L575,555 L540,460 L470,350 L435,245 Z"
                    fill="#1d4ed8" fill-opacity="0.35" stroke="#60a5fa" stroke-width="4"/>
              <circle class="radar" cx="555" cy="215" r="34" fill="none" stroke="#ef4444" stroke-width="5"/>
              <circle cx="555" cy="215" r="12" fill="#ef4444"/>
            </svg>
            <div class="label">{esc_h} {('(' + esc_d + ')') if esc_d else ''}</div></body></html>"""

        # Default: bold animated stat_card
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{font_css}
        body {{ background: linear-gradient(145deg, #111827 0%, #1f2937 100%); color: #f9fafb; }}
        .stat {{ width: 78%; padding: 72px; border: 3px solid #f59e0b; border-radius: 24px; text-align: center;
            background: rgba(17,24,39,0.92); box-shadow: 0 30px 75px rgba(0,0,0,0.65); position: relative; overflow: hidden; }}
        .bar {{ position: absolute; top: 0; left: 0; height: 10px; width: var(--sweep-pct, 100%); background: linear-gradient(90deg, #f59e0b, #ef4444); }}
        .badge {{ display: inline-block; background: #f59e0b; color: #111827; font-weight: 700; font-size: 28px;
            padding: 10px 28px; border-radius: 999px; margin-bottom: 32px; }}
        .val {{ font-size: 62px; line-height: 1.38; font-weight: 700; }}
        </style></head><body><div class="stat">
        <div class="bar"></div>
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

                # Live animated Playwright motion graphics across card types
                if card_type in ("news_card", "stat_card", "phone_call_card", "waveform_card", "map_card"):
                    is_loop = card_type in ("phone_call_card", "waveform_card", "map_card")
                    anim_sec = 1.2 if is_loop else min(1.2, max(0.6, duration * 0.4))
                    n_frames = max(12, int(round(anim_sec * self.fps)))
                    with tempfile.TemporaryDirectory() as frame_dir:
                        page.add_style_tag(content=".highlight { animation: none !important; }")
                        for f_idx in range(n_frames):
                            t_norm = f_idx / max(1, n_frames - 1)
                            eased = 1.0 - (1.0 - t_norm) ** 2.2
                            pct = round(eased * 100.0, 2)
                            page.evaluate(
                                f"document.documentElement.style.setProperty('--sweep-pct', '{pct}%');"
                                f"document.documentElement.style.setProperty('--pulse', '{t_norm:.3f}');"
                                f"document.documentElement.style.setProperty('--phase', '{t_norm:.3f}');"
                            )
                            page.screenshot(path=os.path.join(frame_dir, f"frame_{f_idx:04d}.png"))

                        last_frame = os.path.join(frame_dir, f"frame_{n_frames - 1:04d}.png")
                        head_mp4 = output_path + ".sweep_head.mp4"
                        tail_mp4 = output_path + ".sweep_tail.mp4"
                        rem_dur = max(0.0, duration - (n_frames / float(self.fps)))

                        head_cmd = [
                            "ffmpeg", "-y", "-loglevel", "error",
                            "-framerate", str(self.fps),
                            "-i", os.path.join(frame_dir, "frame_%04d.png"),
                            "-vf", "vignette=PI/5:mode=backward,noise=alls=4:allf=t,format=yuv420p",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                            "-pix_fmt", "yuv420p", "-color_range", "tv",
                            head_mp4,
                        ]
                        res_h = subprocess.run(head_cmd, capture_output=True)
                        ok_anim = False
                        if res_h.returncode == 0 and os.path.exists(head_mp4):
                            if is_loop:
                                res_l = subprocess.run(
                                    [
                                        "ffmpeg", "-y", "-loglevel", "error",
                                        "-stream_loop", "-1", "-i", head_mp4,
                                        "-t", f"{duration:.3f}",
                                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                                        "-pix_fmt", "yuv420p", "-color_range", "tv",
                                        output_path,
                                    ],
                                    capture_output=True,
                                )
                                if os.path.exists(head_mp4):
                                    os.remove(head_mp4)
                                ok_anim = (res_l.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 5000)
                            elif rem_dur >= 0.4 and animate_image_to_video(
                                last_frame, tail_mp4, duration=rem_dur, width=self.width, height=self.height,
                                fps=self.fps, camera=camera, add_film_grain=True,
                            ):
                                res_c = subprocess.run(
                                    [
                                        "ffmpeg", "-y", "-loglevel", "error",
                                        "-i", head_mp4, "-i", tail_mp4,
                                        "-filter_complex", f"[0:v][1:v]concat=n=2:v=1:a=0,fps={self.fps},format=yuv420p[v]",
                                        "-map", "[v]", "-t", f"{duration:.3f}",
                                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p", "-color_range", "tv",
                                        output_path,
                                    ],
                                    capture_output=True,
                                )
                                for tmpf in (head_mp4, tail_mp4):
                                    if os.path.exists(tmpf):
                                        os.remove(tmpf)
                                ok_anim = (res_c.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 5000)
                            else:
                                os.replace(head_mp4, output_path)
                                ok_anim = os.path.exists(output_path) and os.path.getsize(output_path) > 5000
                        if ok_anim:
                            browser.close()
                            return output_path
                        page.screenshot(path=png_tmp)
                        browser.close()
                else:
                    page.wait_for_timeout(1200)
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
        self,
        png_path: str,
        card_type: str,
        headline: str,
        source: str,
        date_badge: str,
        portrait_path: Optional[str] = None,
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

            text_left = px + 56
            if card_type == "quote_card" and portrait_path and os.path.exists(portrait_path):
                try:
                    import io
                    raw_bytes = open(portrait_path, "rb").read()
                    try:
                        from rembg import remove
                        raw_bytes = remove(raw_bytes)
                    except Exception:
                        pass
                    av = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
                    av_sz = min(240, int(self.height * 0.28))
                    av = av.resize((av_sz, av_sz))
                    img.paste(av, (px + 48, py + 72), av)
                    draw.rounded_rectangle([px + 46, py + 70, px + 50 + av_sz, py + 74 + av_sz], radius=12, outline=accent, width=4)
                    text_left = px + 76 + av_sz
                except Exception:
                    pass

            # Use dual-script TTF (Baloo2-Bold / Khand-Bold cover BOTH Latin A-Z and Devanagari + ₹!)
            font_path = resolve_devanagari_font("Baloo2-Bold.ttf") or resolve_devanagari_font("Khand-Bold.ttf")
            use_raqm = check_raqm_support()
            kw = {"layout_engine": ImageFont.Layout.RAQM} if use_raqm else {}
            title_f = ImageFont.truetype(font_path, max(36, self.height // 20), **kw) if font_path else ImageFont.load_default()
            meta_f = ImageFont.truetype(font_path, max(24, self.height // 36), **kw) if font_path else ImageFont.load_default()

            header_txt = f"{source}   |   {date_badge or 'RECORD'}"
            draw.text((text_left, py + 44), header_txt, font=meta_f, fill=accent)

            max_g = 24 if text_left > px + 100 else 32
            lines = wrap_indic_text(headline, max_graphemes=max_g, max_lines=3)
            y_cur = py + 140
            for ln in lines:
                if is_news:
                    bbox = draw.textbbox((text_left, y_cur), ln, font=title_f)
                    draw.rectangle([bbox[0] - 8, bbox[1] - 4, bbox[2] + 8, bbox[3] + 6], fill="#fde047")
                draw.text((text_left, y_cur), ln, font=title_f, fill=fg)
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
            f"Dialogue: 0,0:00:00.00,{format_ass_timestamp(dur)},CardMeta,,0,0,0,,{header}\n"
            f"Dialogue: 0,0:00:00.00,{format_ass_timestamp(dur)},CardMain,,0,0,0,,{body}\n"
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
