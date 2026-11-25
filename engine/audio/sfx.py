"""
engine/audio/sfx.py - Context-Aware Sound Effects Generator
Synthesizes clean, synchronized sound design elements for scene transitions and actions.
"""
import os
import wave
import struct
import math
import random

SAMPLE_RATE = 44100

class SoundEffectsEngine:
    @staticmethod
    def generate_sfx(tag: str, duration: float, output_path: str) -> str:
        """Generate high-fidelity SFX clip matching scene tag."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        dur = max(1.0, float(duration))
        num_samples = int(SAMPLE_RATE * dur)
        samples = [0.0] * num_samples

        tag_lower = tag.lower()

        if "wind" in tag_lower or "ambient" in tag_lower:
            # Gentle ambient wind whoosh
            p = 0.0
            for i in range(num_samples):
                w = random.uniform(-1, 1)
                p = p * 0.96 + w * 0.04
                env = math.sin(math.pi * i / num_samples) ** 1.5
                samples[i] = p * 0.3 * env

        elif "click" in tag_lower or "tool" in tag_lower:
            # Mechanical ratchet clicks at 0.5s intervals
            for beat in [0.4, 1.2, 2.0]:
                si = int(beat * SAMPLE_RATE)
                for c in range(5):
                    ci = si + int(c * 0.06 * SAMPLE_RATE)
                    for j in range(int(0.012 * SAMPLE_RATE)):
                        idx = ci + j
                        if idx < num_samples:
                            decay = (1.0 - j / (0.012 * SAMPLE_RATE)) ** 2
                            samples[idx] += (random.uniform(-0.5, 0.5) + math.sin(2 * math.pi * 2400 * j / SAMPLE_RATE) * 0.3) * decay * 0.4

        elif "chime" in tag_lower or "reveal" in tag_lower:
            # Sparkling harmonic chime
            notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6
            start_i = int(0.3 * SAMPLE_RATE)
            for j in range(int(SAMPLE_RATE * min(3.0, dur - 0.4))):
                idx = start_i + j
                if idx < num_samples:
                    t = j / SAMPLE_RATE
                    decay = math.exp(-t / 0.8)
                    val = sum(math.sin(2 * math.pi * f * t) * (0.15 / (i + 1)) for i, f in enumerate(notes))
                    samples[idx] += val * decay

        else:
            # Cinematic low rumble / cinematic riser
            for i in range(num_samples):
                t = i / SAMPLE_RATE
                freq = 45 + (15 * (i / num_samples))
                env = math.sin(math.pi * i / num_samples) ** 1.8
                samples[i] = math.sin(2 * math.pi * freq * t) * 0.35 * env

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
