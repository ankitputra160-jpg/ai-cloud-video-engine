"""
engine/audio/sfx.py - Context-Aware Foley Sound Design Engine
Loads real CC0 acoustic Foley clips from `assets/sfx/` (`soft_whoosh.wav`, `paper_rustle.wav`,
`marker_stroke.wav`, `subtle_pop.wav`, `deep_sub_hit.wav`, `camera_click.wav`) and places them
precisely at scene openings and 3-5s visual beat transitions.
"""
import logging
import math
import os
import random
import struct
import subprocess
import wave
from typing import Any, Dict, List, Optional

logger = logging.getLogger("audio.sfx")
SAMPLE_RATE = 44100


def get_sfx_dir() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo_root, "assets", "sfx")


def resolve_sfx_clip(tag: str) -> Optional[str]:
    """Map scene mood/visual SFX tag cleanly to bundled Foley WAV asset."""
    sfx_dir = get_sfx_dir()
    low = (tag or "").lower()
    mapping = [
        (("news", "paper", "rustle"), "paper_rustle.wav"),
        (("marker", "highlight", "stroke"), "marker_stroke.wav"),
        (("pop", "stat", "map", "click_tool", "precision"), "subtle_pop.wav"),
        (("camera", "quote", "shutter", "photo"), "camera_click.wav"),
        (("hit", "bass", "rumble", "hook", "hero", "intense", "epic"), "deep_sub_hit.wav"),
        (("whoosh", "wind", "ambient", "soft"), "soft_whoosh.wav"),
    ]
    for keys, fname in mapping:
        if any(k in low for k in keys):
            path = os.path.join(sfx_dir, fname)
            if os.path.exists(path):
                return path
    default_path = os.path.join(sfx_dir, "soft_whoosh.wav")
    return default_path if os.path.exists(default_path) else None


class SoundEffectsEngine:
    @staticmethod
    def generate_sfx(
        tag: str,
        duration: float,
        output_path: str,
        visual_beats: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build scene-length stereo 44.1kHz SFX track aligned to scene start & visual sub-beat transitions."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        dur = max(1.0, float(duration))

        # Place bundled Foley clips at beat transition timestamps when available
        events: List[tuple] = []
        primary_clip = resolve_sfx_clip(tag)
        first_beat_vtype = str(visual_beats[0].get("visual_type", "")) if visual_beats else ""
        if primary_clip:
            events.append((0.02, primary_clip, 0.85))
            if "paper_rustle" in primary_clip or "news_card" in first_beat_vtype:
                if "paper_rustle" not in primary_clip:
                    pr_clip = resolve_sfx_clip("paper_rustle")
                    if pr_clip:
                        events.append((0.03, pr_clip, 0.78))
                marker_clip = resolve_sfx_clip("marker_stroke")
                if marker_clip:
                    events.append((0.45, marker_clip, 0.75))

        if visual_beats and len(visual_beats) > 1:
            cursor = float(visual_beats[0].get("duration", 4.0))
            for beat in visual_beats[1:]:
                b_clip = resolve_sfx_clip(str(beat.get("sfx_tag") or beat.get("visual_type") or "soft_whoosh"))
                if b_clip and cursor < dur - 0.35:
                    events.append((cursor, b_clip, 0.72))
                    if "news_card" in str(beat.get("visual_type", "")):
                        m_clip = resolve_sfx_clip("marker_stroke")
                        if m_clip and (cursor + 0.45) < dur - 0.3:
                            events.append((cursor + 0.45, m_clip, 0.65))
                cursor += float(beat.get("duration", 4.0))

        if events and SoundEffectsEngine._assemble_foley_events(events, dur, output_path):
            return output_path

        # Clean low-level filtered fallback if bundled assets missing
        return SoundEffectsEngine._generate_fallback_sfx(tag, dur, output_path)

    @staticmethod
    def _assemble_foley_events(events: List[tuple], duration: float, output_path: str) -> bool:
        """Overlay triggered Foley WAVs onto clean silent stereo buffer at exact beat timestamps."""
        total_frames = max(SAMPLE_RATE, int(round(duration * SAMPLE_RATE)))
        left = [0.0] * total_frames
        right = [0.0] * total_frames

        for start_s, wav_path, gain in events:
            try:
                with wave.open(wav_path, "rb") as w:
                    ch = w.getnchannels()
                    raw = w.readframes(w.getnframes())
                n_vals = len(raw) // 2
                ints = struct.unpack(f"<{n_vals}h", raw[:n_vals * 2])
                offset = max(0, int(round(start_s * SAMPLE_RATE)))
                if ch == 2:
                    n_src = len(ints) // 2
                    for k in range(n_src):
                        dst = offset + k
                        if dst >= total_frames:
                            break
                        left[dst] += (ints[2 * k] / 32768.0) * gain
                        right[dst] += (ints[2 * k + 1] / 32768.0) * gain
                else:
                    for k, val in enumerate(ints):
                        dst = offset + k
                        if dst >= total_frames:
                            break
                        s = (val / 32768.0) * gain
                        left[dst] += s
                        right[dst] += s
            except Exception as e:
                logger.debug(f"Foley clip load skipped ({wav_path}): {e}")

        buf = bytearray()
        for l_v, r_v in zip(left, right):
            lv = int(max(-32767, min(32767, l_v * 32767.0)))
            rv = int(max(-32767, min(32767, r_v * 32767.0)))
            buf.extend(struct.pack("<hh", lv, rv))

        with wave.open(output_path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(bytes(buf))
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000

    @staticmethod
    def _generate_fallback_sfx(tag: str, dur: float, output_path: str) -> str:
        num_samples = int(SAMPLE_RATE * dur)
        samples = [0.0] * num_samples
        p = 0.0
        for i in range(min(num_samples, int(SAMPLE_RATE * 1.2))):
            w = random.uniform(-1, 1)
            p = p * 0.96 + w * 0.04
            env = math.sin(math.pi * i / min(num_samples, int(SAMPLE_RATE * 1.2))) ** 1.5
            samples[i] = p * 0.25 * env

        with wave.open(output_path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            raw_bytes = bytearray()
            for s in samples:
                val = int(max(-32767, min(32767, s * 32767)))
                packed = struct.pack("<h", val)
                raw_bytes.extend(packed)
                raw_bytes.extend(packed)
            w.writeframes(raw_bytes)
        return output_path
