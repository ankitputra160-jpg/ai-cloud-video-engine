"""
engine/audio/bgm.py - Thematic Background Music Engine
Synthesizes rich, harmonic documentary musical scores based on chapter mood.
"""
import os
import wave
import struct
import math
import random
from typing import Dict, List

SAMPLE_RATE = 44100

class BackgroundMusicEngine:
    MOOD_HARMONIES = {
        "mysterious": [[110.0, 130.81, 164.81, 196.0], [98.0, 123.47, 146.83, 174.61]],  # A minor, G minor
        "curious": [[130.81, 164.81, 196.0, 246.94], [146.83, 174.61, 220.0, 261.63]],     # C maj7, D min7
        "intense": [[82.41, 123.47, 164.81], [73.42, 110.0, 146.83]],                       # E power, D power
        "focused": [[146.83, 185.0, 220.0, 261.63], [130.81, 164.81, 196.0, 246.94]],      # D acoustic, C maj
        "inspiring": [[174.61, 220.0, 261.63, 329.63], [196.0, 246.94, 293.66, 392.0]],    # F maj7, G maj
        "epic": [[110.0, 164.81, 220.0, 329.63], [130.81, 196.0, 261.63, 392.0]]          # A epic, C epic
    }

    @classmethod
    def generate_thematic_bgm(cls, output_path: str, duration: float, mood: str = "inspiring") -> str:
        """Compose and render continuous atmospheric background score matching documentary mood."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        dur = max(4.0, float(duration))
        num_samples = int(SAMPLE_RATE * dur)
        samples = [0.0] * num_samples

        chords = cls.MOOD_HARMONIES.get(mood, cls.MOOD_HARMONIES["inspiring"])
        chord_duration = 4.0
        total_chords = int(math.ceil(dur / chord_duration))

        for ci in range(total_chords):
            chord = chords[ci % len(chords)]
            start_idx = int(ci * chord_duration * SAMPLE_RATE)
            chord_len = int(chord_duration * SAMPLE_RATE)

            for j in range(chord_len):
                idx = start_idx + j
                if idx >= num_samples:
                    break
                t = j / SAMPLE_RATE
                # Smooth slow envelope for documentary cinematic feel
                env = math.sin(math.pi * j / chord_len) ** 1.3
                val = 0.0
                for note_idx, freq in enumerate(chord):
                    # Fundamental note
                    val += math.sin(2 * math.pi * freq * t) * (0.08 / (note_idx + 1))
                    # Warm analog overtone
                    val += math.sin(2 * math.pi * (freq * 2.01) * t) * 0.02
                samples[idx] += val * env

        # Master gain normalization and soft fade-in/fade-out
        max_val = max((abs(x) for x in samples), default=1.0) or 1.0
        fade_samples = int(SAMPLE_RATE * 1.5)
        
        normalized = []
        for i, s in enumerate(samples):
            # 1.5s fade in, 2s fade out
            gain = 1.0
            if i < fade_samples:
                gain = i / fade_samples
            elif i > num_samples - fade_samples:
                gain = (num_samples - i) / fade_samples
            normalized.append((s / max_val) * 0.35 * gain)

        with wave.open(output_path, "wb") as w:
            w.setnchannels(2)  # Stereo
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            raw_bytes = bytearray()
            for s in normalized:
                val = int(max(-32767, min(32767, s * 32767)))
                packed = struct.pack("<h", val)
                raw_bytes.extend(packed)  # Left
                raw_bytes.extend(packed)  # Right
            w.writeframes(raw_bytes)

        return output_path
