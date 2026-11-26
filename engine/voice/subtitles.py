"""
engine/voice/subtitles.py - Dynamic Word-Synced Subtitle Engine (.srt & .ass)
Builds rhythmic 3-5 word chunks with Devanagari NFC & grapheme-safe wrapping,
plus styled ASS karaoke/pill-box captions rendered cleanly by libass + HarfBuzz.
"""
import os
from typing import Any, Dict, List

from engine.storyboard import SceneDefinition, StoryboardManifest
from engine.text.devanagari import contains_devanagari, normalize_devanagari, wrap_indic_text


class SubtitleGenerator:
    @staticmethod
    def format_timestamp_srt(seconds: float) -> str:
        """Format seconds into SRT timestamp HH:MM:SS,mmm"""
        seconds = max(0.0, float(seconds))
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000)) % 1000
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def format_timestamp_ass(seconds: float) -> str:
        """Format seconds into ASS timestamp H:MM:SS.cc"""
        seconds = max(0.0, float(seconds))
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int(round((seconds - int(seconds)) * 100))
        if centis >= 100:
            secs += 1
            centis = 0
        return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"

    @classmethod
    def _scene_chunks(cls, scene: SceneDefinition, words_per_chunk: int = 5) -> List[Dict[str, Any]]:
        """Group scene word timings (or text tokens) into readable 3-5 word timed chunks."""
        timings = getattr(scene, "word_timings", None) or []
        if not timings:
            clean = normalize_devanagari(scene.subtitle_text or scene.narration)
            tokens = [t for t in clean.split(" ") if t]
            if not tokens:
                return []
            usable = max(1.0, scene.duration - 0.5)
            per_word = usable / len(tokens)
            timings = [
                {"text": tok, "start": round(0.2 + i * per_word, 3), "end": round(0.2 + (i + 1) * per_word, 3)}
                for i, tok in enumerate(tokens)
            ]

        chunks: List[Dict[str, Any]] = []
        for idx in range(0, len(timings), words_per_chunk):
            group = timings[idx:idx + words_per_chunk]
            raw_phrase = " ".join(w["text"] for w in group)
            wrapped_lines = wrap_indic_text(raw_phrase, max_graphemes=36, max_lines=2)
            chunks.append({
                "start": float(group[0]["start"]),
                "end": min(scene.duration - 0.05, float(group[-1]["end"]) + 0.08),
                "words": group,
                "lines": wrapped_lines or [raw_phrase],
            })
        return chunks

    @classmethod
    def generate_srt(cls, manifest: StoryboardManifest, output_path: str) -> str:
        """Create a rhythmic chunked SubRip (.srt) subtitle file from the storyboard manifest."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        current_time = 0.0
        srt_entries: List[str] = []
        cue_index = 1

        for scene in manifest.scenes:
            chunks = cls._scene_chunks(scene, words_per_chunk=5)
            if not chunks:
                clean_text = "\n".join(wrap_indic_text(scene.subtitle_text, max_graphemes=38))
                start_t = current_time + 0.25
                end_t = current_time + max(1.0, scene.duration - 0.25)
                srt_entries.append(
                    f"{cue_index}\n"
                    f"{cls.format_timestamp_srt(start_t)} --> {cls.format_timestamp_srt(end_t)}\n"
                    f"{clean_text}\n"
                )
                cue_index += 1
            else:
                for ch in chunks:
                    start_t = current_time + ch["start"]
                    end_t = current_time + max(ch["start"] + 0.3, ch["end"])
                    text_block = "\n".join(ch["lines"])
                    srt_entries.append(
                        f"{cue_index}\n"
                        f"{cls.format_timestamp_srt(start_t)} --> {cls.format_timestamp_srt(end_t)}\n"
                        f"{text_block}\n"
                    )
                    cue_index += 1

            current_time += scene.duration

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_entries))

        return output_path

    @classmethod
    def _build_ass_header(cls, width: int, height: int, language: str, style_mode: str = "ass_karaoke") -> str:
        """Build ASS script header with Noto Sans Devanagari for HarfBuzz complex script shaping."""
        is_hindi = language == "hi"
        font_name = "Noto Sans Devanagari" if is_hindi else "Arial"
        font_size = max(34, int(height * 0.044)) if is_hindi else max(38, int(height * 0.046))
        margin_v = max(48, int(height * 0.068))
        # BorderStyle=4 renders translucent dark documentary plate behind words
        border_style = 4 if style_mode in ("ass_karaoke", "pill_box") else 1
        outline_px = 14 if border_style == 4 else 3

        # In ASS \kf karaoke, SecondaryColour fills into PrimaryColour as words are spoken
        primary_col = "&H0000D7FF" if style_mode == "ass_karaoke" else "&H00FFFFFF"
        secondary_col = "&H00FFFFFF" if style_mode == "ass_karaoke" else "&H0000D7FF"

        return (
            "[Script Info]\n"
            "Title: AI Documentary Dynamic Subtitles\n"
            "ScriptType: v4.00+\n"
            "WrapStyle: 0\n"
            f"PlayResX: {width}\n"
            f"PlayResY: {height}\n"
            "ScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: DocCaption,{font_name},{font_size},{primary_col},{secondary_col},&H00101520,&HCC0F172A,"
            f"-1,0,0,0,100,100,0,0,{border_style},{outline_px},0,2,80,80,{margin_v},1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

    @classmethod
    def _format_chunk_dialogue(
        cls, start_abs: float, end_abs: float, chunk: Dict[str, Any], style_mode: str
    ) -> str:
        """Format a chunk dialogue event with smooth fade and optional active karaoke fill."""
        start_s = cls.format_timestamp_ass(start_abs)
        end_s = cls.format_timestamp_ass(max(start_abs + 0.3, end_abs))

        if style_mode == "ass_karaoke" and chunk.get("words"):
            # Use \kf centisecond sweep highlight per word (gold -> crisp white)
            # Note: In ASS karaoke, SecondaryColour (&H0000D7FF gold) sweeps to PrimaryColour (&H00FFFFFF white)
            parts: List[str] = []
            words = chunk["words"]
            break_after = len(words) // 2 if len(words) >= 4 else -1
            for w_idx, w in enumerate(words):
                dur_cs = max(12, int(round((float(w["end"]) - float(w["start"])) * 100)))
                word_txt = normalize_devanagari(w["text"]).replace("{", "").replace("}", "")
                parts.append(f"{{\\kf{dur_cs}}}{word_txt}")
                if w_idx == break_after:
                    parts.append("\\N")
                elif w_idx < len(words) - 1:
                    parts.append(" ")
            body = "".join(parts)
            return f"Dialogue: 0,{start_s},{end_s},DocCaption,,0,0,0,,{{\\fad(70,70)}}{body}"

        body = "\\N".join(chunk["lines"]).replace("{", "").replace("}", "")
        return f"Dialogue: 0,{start_s},{end_s},DocCaption,,0,0,0,,{{\\fad(80,80)}}{body}"

    @classmethod
    def generate_ass(
        cls,
        manifest: StoryboardManifest,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
        style_mode: str = "ass_karaoke",
    ) -> str:
        """Create full styled ASS subtitle track synchronized across all scenes."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        lines = [cls._build_ass_header(width, height, manifest.language, style_mode)]

        current_time = 0.0
        for scene in manifest.scenes:
            chunks = cls._scene_chunks(scene, words_per_chunk=5)
            for ch in chunks:
                lines.append(
                    cls._format_chunk_dialogue(
                        current_time + ch["start"],
                        current_time + ch["end"],
                        ch,
                        style_mode,
                    )
                )
            current_time += scene.duration

        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines) + "\n")
        return output_path

    @classmethod
    def generate_scene_ass(
        cls,
        scene: SceneDefinition,
        output_path: str,
        language: str = "en",
        width: int = 1920,
        height: int = 1080,
        style_mode: str = "ass_karaoke",
    ) -> str:
        """Create standalone 0-indexed ASS subtitle file for a single scene (for scalable chunk rendering)."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        lines = [cls._build_ass_header(width, height, language, style_mode)]
        for ch in cls._scene_chunks(scene, words_per_chunk=5):
            lines.append(cls._format_chunk_dialogue(ch["start"], ch["end"], ch, style_mode))

        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines) + "\n")
        return output_path
