"""
engine/voice/aligner.py - CTC Forced Alignment (facebook/mms-300m) & Speak-to-Show Span Mapper
Forces pre-written phonetic Devanagari `speak_words` onto synthesized audio via ctc-forced-aligner
with uroman (`language="hin"`), returning exact [start_s, end_s] timestamps mapped back to
compact display `span_id` chunks (e.g., "पाँच सौ करोड़ रुपये" -> "₹500 Cr") so compounds never split.
Includes automatic proportional alignment fallback on CPU/offline environments.
"""
import gc
import logging
import re
from typing import Any, Dict, List, Optional

from engine.text.devanagari import normalize_devanagari

logger = logging.getLogger("voice.aligner")


class ForcedAligner:
    """Manages Meta MMS-300M CTC forced alignment + Stage-Gate VRAM unload."""

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._checked = False

    def is_ctc_available(self) -> bool:
        try:
            import ctc_forced_aligner  # noqa: F401
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _load_model(self) -> bool:
        if self._checked:
            return self._model is not None
        self._checked = True
        try:
            import torch
            from ctc_forced_aligner import load_alignment_model
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            logger.info(f"Loading MMS-300M CTC forced-aligner on {device}...")
            self._model, self._tokenizer = load_alignment_model(device, dtype=dtype)
            return True
        except Exception as e:
            logger.debug(f"ctc-forced-aligner unavailable, using proportional timing aligner: {e}")
            return False

    def unload(self) -> None:
        """Unload MMS-300M cleanly to reset VRAM to 0 GB before visual stages."""
        for attr in ("_model", "_tokenizer"):
            val = getattr(self, attr, None)
            if val is not None:
                try:
                    del val
                except Exception:
                    pass
                setattr(self, attr, None)
        self._checked = False
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def align_speak_words(
        self,
        audio_path: str,
        speak_words: List[str],
        audio_duration: float,
        language: str = "hin",
    ) -> List[Dict[str, Any]]:
        """Return exact [{text, start, end}, ...] for every word in `speak_words`."""
        clean_words = [normalize_devanagari(w) for w in speak_words if w and w.strip()]
        if not clean_words:
            return []

        if self.is_ctc_available() and self._load_model():
            try:
                from ctc_forced_aligner import (
                    generate_emissions,
                    get_alignments,
                    get_spans,
                    load_audio,
                    postprocess_results,
                    preprocess_text,
                )
                transcript = " ".join(clean_words)
                waveform = load_audio(audio_path, self._model.dtype, self._model.device)
                emissions, stride = generate_emissions(self._model, waveform, batch_size=16)
                iso_lang = "hin" if language in ("hi", "hin") else "eng"
                tokens_starred, text_starred = preprocess_text(
                    transcript,
                    romanize=True,
                    language=iso_lang,
                )
                segments, scores, blank_token = get_alignments(emissions, tokens_starred, self._tokenizer)
                spans = get_spans(tokens_starred, segments, blank_token)
                raw_results = postprocess_results(text_starred, spans, stride, scores)

                if len(raw_results) >= len(clean_words):
                    aligned = []
                    for idx, orig_word in enumerate(clean_words):
                        item = raw_results[idx]
                        st = float(item.get("start", 0.0))
                        en = max(st + 0.06, float(item.get("end", st + 0.15)))
                        aligned.append({"text": orig_word, "start": round(st, 3), "end": round(en, 3)})
                    return aligned
            except Exception as e:
                logger.warning(f"CTC alignment fallback for {audio_path}: {e}")

        return self.estimate_proportional_timings(clean_words, audio_duration)

    @staticmethod
    def estimate_proportional_timings(words: List[str], audio_duration: float) -> List[Dict[str, Any]]:
        """Weighted proportional fallback timed strictly against exact probed WAV duration."""
        if not words:
            return []
        dur = max(0.5, float(audio_duration))
        usable = max(0.4, dur - 0.12)
        weights = [max(1, len(re.sub(r"\s+", "", w))) for w in words]
        total_w = sum(weights) or len(words)
        cursor = 0.06
        out: List[Dict[str, Any]] = []
        for word, wt in zip(words, weights):
            seg = usable * (wt / total_w)
            out.append({
                "text": word,
                "start": round(cursor, 3),
                "end": round(min(dur - 0.02, cursor + seg), 3),
            })
            cursor += seg
        return out

    @staticmethod
    def map_speak_timings_to_show_spans(
        speak_word_timings: List[Dict[str, Any]],
        display_spans: List[Dict[str, Any]],
        audio_duration: float,
    ) -> List[Dict[str, Any]]:
        """Map exact start/end timestamps from spoken Devanagari words back to atomic `show` spans.

        Guarantees that compound display spans like '₹500 Cr' or 'Supreme Court' get a single
        start/end interval and atomic `span_id` so SubtitleGenerator never breaks them across lines.
        """
        if not display_spans or not speak_word_timings:
            return speak_word_timings

        max_idx = len(speak_word_timings) - 1
        mapped: List[Dict[str, Any]] = []
        for sp in display_spans:
            s_idx = min(max(0, int(sp.get("speak_start_idx", 0))), max_idx)
            e_idx = min(max(s_idx, int(sp.get("speak_end_idx", s_idx))), max_idx)
            start_t = float(speak_word_timings[s_idx]["start"])
            end_t = min(float(audio_duration) - 0.02, max(start_t + 0.08, float(speak_word_timings[e_idx]["end"])))
            mapped.append({
                "span_id": sp.get("span_id", f"span_{len(mapped) + 1}"),
                "text": normalize_devanagari(sp.get("show", "")),
                "start": round(start_t, 3),
                "end": round(end_t, 3),
            })
        return [m for m in mapped if m["text"]]
