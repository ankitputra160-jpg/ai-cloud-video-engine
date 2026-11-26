"""
engine/audio/bgm.py - Pre-Indexed 4-Mood CC0 Background Music Bank & Soft Pad Fallback
Supports Google Drive cached royalty-free / CC0 documentary tracks across 4 mood folders:
  - investigative_pulse
  - somber_emotional
  - historical_epic
  - neutral_explainer
Rotates tracks per chapter with smooth transitions and falls back cleanly to a warm low sub-pad
when running offline (eliminating harsh raw chord overtones).
"""
import logging
import math
import os
import struct
import subprocess
import urllib.request
import wave
from typing import Dict, List, Optional

logger = logging.getLogger("audio.bgm")
SAMPLE_RATE = 44100

MOOD_FOLDER_MAP: Dict[str, str] = {
    "mysterious": "investigative_pulse",
    "intense": "investigative_pulse",
    "focused": "neutral_explainer",
    "curious": "neutral_explainer",
    "inspiring": "historical_epic",
    "epic": "historical_epic",
    "somber": "somber_emotional",
}

# Verified CC0 / Public Domain starter documentary music beds fetched once onto Google Drive on Colab
CC0_STARTER_URLS: Dict[str, List[str]] = {
    "investigative_pulse": [
        "https://freepd.com/music/Thinking%20Time.mp3",
        "https://freepd.com/music/Mystery%20Sax.mp3",
    ],
    "somber_emotional": [
        "https://freepd.com/music/Sad%20Trio.mp3",
    ],
    "historical_epic": [
        "https://freepd.com/music/Chronos.mp3",
    ],
    "neutral_explainer": [
        "https://freepd.com/music/Study%20and%20Relax.mp3",
    ],
}


def bootstrap_cc0_bgm_bank(bank_dir: str, timeout: int = 25) -> Dict[str, List[str]]:
    """Download CC0 background music beds once into Google Drive mood folders (cached permanently)."""
    os.makedirs(bank_dir, exist_ok=True)
    indexed: Dict[str, List[str]] = {}
    for folder, urls in CC0_STARTER_URLS.items():
        sub = os.path.join(bank_dir, folder)
        os.makedirs(sub, exist_ok=True)
        files_here = [os.path.join(sub, f) for f in os.listdir(sub) if f.lower().endswith((".mp3", ".wav", ".ogg"))]
        if not files_here:
            for idx, url in enumerate(urls):
                dest = os.path.join(sub, f"cc0_{folder}_{idx + 1}.mp3")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/3.0"})
                    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
                        if resp.status == 200:
                            out.write(resp.read())
                    if os.path.exists(dest) and os.path.getsize(dest) > 20000:
                        files_here.append(dest)
                    elif os.path.exists(dest):
                        os.remove(dest)
                except Exception as e:
                    logger.debug(f"CC0 BGM fetch skipped for {url}: {e}")
                    if os.path.exists(dest):
                        os.remove(dest)
        indexed[folder] = sorted(files_here)
    return indexed


class BackgroundMusicEngine:
    # Warm low documentary sub-pad chords (offline fallback when Drive CC0 bank unavailable)
    MOOD_HARMONIES: Dict[str, List[List[float]]] = {
        "mysterious": [[65.41, 98.00, 130.81], [61.74, 92.50, 123.47]],
        "curious": [[73.42, 110.00, 146.83], [65.41, 98.00, 130.81]],
        "intense": [[55.00, 82.41, 110.00], [49.00, 73.42, 98.00]],
        "focused": [[73.42, 110.00, 164.81], [65.41, 98.00, 146.83]],
        "inspiring": [[87.31, 130.81, 174.61], [98.00, 146.83, 196.00]],
        "epic": [[55.00, 82.41, 110.00, 164.81], [65.41, 98.00, 130.81, 196.00]],
    }

    @classmethod
    def pick_cc0_track(
        cls, bgm_bank_dir: Optional[str], mood: str = "curious", chapter_index: int = 0
    ) -> Optional[str]:
        """Select a pre-downloaded CC0 track matching documentary mood (rotated every chapter)."""
        if not bgm_bank_dir or not os.path.isdir(bgm_bank_dir):
            return None
        folder = MOOD_FOLDER_MAP.get(mood, "neutral_explainer")
        candidate_dir = os.path.join(bgm_bank_dir, folder)
        if not os.path.isdir(candidate_dir):
            candidate_dir = bgm_bank_dir
        tracks = sorted(
            os.path.join(candidate_dir, f)
            for f in os.listdir(candidate_dir)
            if f.lower().endswith((".mp3", ".wav", ".ogg", ".m4a"))
        )
        if not tracks:
            return None
        return tracks[chapter_index % len(tracks)]

    @classmethod
    def generate_thematic_bgm(
        cls,
        output_path: str,
        duration: float,
        mood: str = "inspiring",
        bgm_bank_dir: Optional[str] = None,
        chapter_index: int = 0,
    ) -> str:
        """Prepare chapter BGM from CC0 Drive bank (preferred) or soft warm stereo sub-pad."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        dur = max(2.0, float(duration))

        track = cls.pick_cc0_track(bgm_bank_dir, mood=mood, chapter_index=chapter_index)
        if track and os.path.exists(track):
            # Rotate start offset every chapter so continuous documentaries stay fresh
            offset = (chapter_index * 18) % 60
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-stream_loop", "-1", "-ss", str(offset), "-i", track,
                "-t", f"{dur:.3f}",
                "-af", f"afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.2, dur - 0.8):.3f}:d=0.8",
                "-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_s16le",
                output_path,
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 2000:
                return output_path

        return cls._synthesize_soft_sub_pad(output_path, dur, mood)

    @classmethod
    def _synthesize_soft_sub_pad(cls, output_path: str, dur: float, mood: str) -> str:
        """Generate subtle low-passed documentary sub-pad (unobtrusive beneath speech)."""
        num_samples = int(SAMPLE_RATE * dur)
        samples = [0.0] * num_samples

        chords = cls.MOOD_HARMONIES.get(mood, cls.MOOD_HARMONIES["curious"])
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
                env = math.sin(math.pi * j / chord_len) ** 1.4
                val = sum(math.sin(2 * math.pi * f * t) * (0.06 / (n_i + 1)) for n_i, f in enumerate(chord))
                samples[idx] += val * env

        max_val = max((abs(x) for x in samples), default=1.0) or 1.0
        fade_samples = min(num_samples // 4, int(SAMPLE_RATE * 1.0))

        with wave.open(output_path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            raw_bytes = bytearray()
            for i, s in enumerate(samples):
                gain = 1.0
                if i < fade_samples:
                    gain = i / max(1, fade_samples)
                elif i > num_samples - fade_samples:
                    gain = (num_samples - i) / max(1, fade_samples)
                val = int(max(-32767, min(32767, ((s / max_val) * 0.28 * gain) * 32767)))
                packed = struct.pack("<h", val)
                raw_bytes.extend(packed)
                raw_bytes.extend(packed)
            w.writeframes(raw_bytes)
        return output_path
