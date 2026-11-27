"""
engine/voice/subtitles.py - Dynamic Word-Synced Dual-Layer Subtitle Engine (.srt & .ass)
Implements Span-ID Chunk Locking (never splitting atomic display spans like '₹500 Cr' or
'Supreme Court' across two lines), 3-5 word / <= 30 grapheme chunks, Devanagari NFC & \\X wrapping,
and libass karaoke/pill-box styling backed by static Noto Sans Devanagari fonts.
"""
import os
from typing import Any, Dict, List

from engine.storyboard import SceneDefinition, StoryboardManifest
from engine.text.devanagari import grapheme_len, normalize_devanagari, wrap_indic_text


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
    def _scene_chunks(
        cls, scene: SceneDefinition, words_per_chunk: int = 5, max_chunk_graphemes: int = 30
    ) -> List[Dict[str, Any]]:
        """Group word timings into 3-5 word / <=30-grapheme chunks without splitting atomic span_ids."""
        timings = getattr(scene, "word_timings", None) or []
        if not timings:
            clean = normalize_devanagari(scene.subtitle_text or scene.narration)
            tokens = [t for t in clean.split(" ") if t]
            if not tokens:
                return []
            usable = max(0.8, scene.duration - 0.3)
            per_word = usable / len(tokens)
            timings = [
                {
                    "text": tok,
                    "span_id": f"tok_{i+1}",
                    "start": round(0.1 + i * per_word, 3),
                    "end": round(0.1 + (i + 1) * per_word, 3),
                }
                for i, tok in enumerate(tokens)
            ]

        chunks: List[Dict[str, Any]] = []
        current_group: List[Dict[str, Any]] = []
        current_g_len = 0

        for wt in timings:
            tok_txt = normalize_devanagari(str(wt.get("text", "")))
            if not tok_txt:
                continue
            tok_len = grapheme_len(tok_txt)
            projected_len = current_g_len + tok_len + (1 if current_group else 0)

            if current_group and (len(current_group) >= words_per_chunk or projected_len > max_chunk_graphemes):
                chunks.append(cls._finalize_chunk(current_group, scene.duration))
                current_group = [wt]
                current_g_len = tok_len
            else:
                current_group.append(wt)
                current_g_len = projected_len

        if current_group:
            chunks.append(cls._finalize_chunk(current_group, scene.duration))

        # Avoid 1-word trailing orphan subtitles by balancing with the previous chunk
        if len(chunks) >= 2 and len(chunks[-1]["words"]) == 1 and len(chunks[-2]["words"]) >= 3:
            prev_words = chunks[-2]["words"]
            last_words = chunks[-1]["words"]
            moved = prev_words[-1:]
            chunks[-2] = cls._finalize_chunk(prev_words[:-1], scene.duration)
            chunks[-1] = cls._finalize_chunk(moved + last_words, scene.duration)

        # Prevent adjacent subtitle box overlap in libass
        for i in range(len(chunks) - 1):
            nxt_start = float(chunks[i + 1]["start"])
            if chunks[i]["end"] >= nxt_start:
                chunks[i]["end"] = round(max(chunks[i]["start"] + 0.15, nxt_start - 0.01), 3)

        return chunks

    @staticmethod
    def _finalize_chunk(group: List[Dict[str, Any]], scene_duration: float) -> Dict[str, Any]:
        """Keep each chunk concise (1 line when <=30 graphemes, or clean atomic-span 2 lines)."""
        raw_phrase = " ".join(normalize_devanagari(str(w["text"])) for w in group)
        if grapheme_len(raw_phrase) <= 32:
            wrapped_lines = [raw_phrase]
        else:
            # Atomic span-level wrapping so no span like '₹500 Cr' or 'Supreme Court' ever splits
            mid = max(1, len(group) // 2)
            l1 = " ".join(normalize_devanagari(str(w["text"])) for w in group[:mid])
            l2 = " ".join(normalize_devanagari(str(w["text"])) for w in group[mid:])
            wrapped_lines = [l for l in (l1, l2) if l]

        return {
            "start": float(group[0]["start"]),
            "end": min(max(0.25, scene_duration - 0.02), float(group[-1]["end"]) + 0.06),
            "words": group,
            "lines": wrapped_lines or [raw_phrase],
        }

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
                clean_text = "\n".join(wrap_indic_text(scene.subtitle_text, max_graphemes=30))
                start_t = current_time + 0.15
                end_t = current_time + max(0.8, scene.duration - 0.15)
                srt_entries.append(
                    f"{cue_index}\n"
                    f"{cls.format_timestamp_srt(start_t)} --> {cls.format_timestamp_srt(end_t)}\n"
                    f"{clean_text}\n"
                )
                cue_index += 1
            else:
                for ch in chunks:
                    start_t = current_time + ch["start"]
                    end_t = current_time + max(ch["start"] + 0.25, ch["end"])
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
        """Build ASS script header referencing static Noto Sans Devanagari for HarfBuzz shaping."""
        is_hindi = language == "hi"
        font_name = "Noto Sans Devanagari" if is_hindi else "Arial"
        font_size = max(36, int(height * 0.046)) if is_hindi else max(38, int(height * 0.046))
        margin_v = max(52, int(height * 0.072))
        border_style = 4 if style_mode in ("ass_karaoke", "pill_box") else 1
        outline_px = 14 if border_style == 4 else 3

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
        """Format chunk dialogue event while keeping atomic spans unbroken."""
        start_s = cls.format_timestamp_ass(start_abs)
        end_s = cls.format_timestamp_ass(max(start_abs + 0.25, end_abs))

        if style_mode == "ass_karaoke" and chunk.get("words"):
            parts: List[str] = []
            words = chunk["words"]
            total_graphemes = sum(grapheme_len(str(w["text"])) for w in words)
            break_after = len(words) // 2 if (total_graphemes > 32 and len(words) >= 4) else -1
            for w_idx, w in enumerate(words):
                dur_cs = max(12, int(round((float(w["end"]) - float(w["start"])) * 100)))
                word_txt = normalize_devanagari(str(w["text"])).replace("{", "").replace("}", "")
                parts.append(f"{{\\kf{dur_cs}}}{word_txt}")
                if w_idx == break_after:
                    parts.append("\\N")
                elif w_idx < len(words) - 1:
                    parts.append(" ")
            body = "".join(parts)
            return f"Dialogue: 0,{start_s},{end_s},DocCaption,,0,0,0,,{{\\fad(60,60)}}{body}"

        body = "\\N".join(chunk["lines"]).replace("{", "").replace("}", "")
        return f"Dialogue: 0,{start_s},{end_s},DocCaption,,0,0,0,,{{\\fad(70,70)}}{body}"

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
        """Create standalone 0-indexed ASS subtitle file for single scene chunk rendering."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        lines = [cls._build_ass_header(width, height, language, style_mode)]
        for ch in cls._scene_chunks(scene, words_per_chunk=5):
            lines.append(cls._format_chunk_dialogue(ch["start"], ch["end"], ch, style_mode))

        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines) + "\n")
        return output_path
