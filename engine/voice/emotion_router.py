"""
engine/voice/emotion_router.py - ElevenLabs-Style Inline Emotion & Pause Tag Router
Parses strict inline prosody markup ([pause:Xs], [fear], [angry], [slow], [fast]),
routes each speech block to matching mood reference/caption + FFmpeg pitch-preserving
speed DSP using actual probed sample rates (fixing 24kHz vs 44.1kHz drift),
inserts natural -65dB studio room tone for pauses, and stitches via 20ms fades.
Works cleanly with optional numpy/soundfile OR pure stdlib wave on Termux/CPU.
"""
import logging
import math
import os
import random
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("voice.emotion_router")

STANDARD_OUTPUT_SR = 44100

EMOTION_PROFILES: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "parler_caption": (
            "Tapan speaks at a moderate pace with a warm, engaging Indian documentary tone. "
            "Very clear audio, close mic studio recording."
        ),
        "ref_filename": "ref_neutral.wav",
        "atempo": 1.00,
        "pitch_shift": 1.00,
    },
    "fear": {
        "parler_caption": (
            "Tapan speaks slowly with a lower pitch and tense, suspenseful emotional depth. "
            "Very clear audio, close mic studio recording."
        ),
        "ref_filename": "ref_suspense.wav",
        "atempo": 0.91,
        "pitch_shift": 0.96,
    },
    "angry": {
        "parler_caption": (
            "Tapan speaks with urgent intensity, crisp emphasis, and strong emotional conviction. "
            "Very clear audio, close mic studio recording."
        ),
        "ref_filename": "ref_angry.wav",
        "atempo": 1.05,
        "pitch_shift": 1.02,
    },
    "slow": {
        "parler_caption": (
            "Tapan speaks slowly and deliberately, pausing briefly to emphasize key facts. "
            "Very clear audio, close mic studio recording."
        ),
        "ref_filename": "ref_neutral.wav",
        "atempo": 0.88,
        "pitch_shift": 0.98,
    },
    "fast": {
        "parler_caption": (
            "Tapan speaks at an energetic, faster conversational pace with crisp clarity. "
            "Very clear audio, close mic studio recording."
        ),
        "ref_filename": "ref_fast.wav",
        "atempo": 1.12,
        "pitch_shift": 1.01,
    },
}

TAG_PATTERN = re.compile(
    r"(\[pause:\s*\d+(?:\.\d+)?s\s*\]|\[(fear|angry|slow|fast)\](.*?)\[/\2\])",
    flags=re.DOTALL | re.IGNORECASE,
)


def parse_emotion_script(text: str, max_emotion_shifts: int = 2) -> List[Dict[str, Any]]:
    """Parse inline emotion & pause tags into ordered speech/pause segments."""
    if not text:
        return []
    segments: List[Dict[str, Any]] = []
    last_idx = 0
    shifts_used = 0

    for match in TAG_PATTERN.finditer(text):
        if match.start() > last_idx:
            plain = text[last_idx:match.start()].strip()
            if plain:
                segments.append({"type": "speech", "emotion": "neutral", "text": plain})

        full_tag = match.group(0)
        if full_tag.lower().startswith("[pause:"):
            sec_match = re.search(r"\d+(?:\.\d+)?", full_tag)
            dur = float(sec_match.group(0)) if sec_match else 0.4
            segments.append({"type": "pause", "duration": round(min(max(dur, 0.1), 3.0), 3)})
        else:
            emotion = match.group(2).lower()
            inner_text = match.group(3).strip()
            if inner_text:
                if shifts_used >= max_emotion_shifts:
                    emotion = "neutral"
                else:
                    shifts_used += 1
                segments.append({"type": "speech", "emotion": emotion, "text": inner_text})

        last_idx = match.end()

    if last_idx < len(text):
        tail = text[last_idx:].strip()
        if tail:
            segments.append({"type": "speech", "emotion": "neutral", "text": tail})

    # Clean any stray unclosed bracket tags left behind
    cleaned_segments: List[Dict[str, Any]] = []
    for seg in segments:
        if seg["type"] == "speech":
            clean_txt = re.sub(r"\[/?[a-zA-Z0-9_:.]+\]", "", seg["text"]).strip()
            if clean_txt:
                cleaned_segments.append({**seg, "text": clean_txt})
        else:
            cleaned_segments.append(seg)
    return cleaned_segments


def probe_wav_sample_rate(wav_path: str, fallback: int = 24000) -> int:
    """Read exact native sample rate of any WAV file so DSP never shifts pitch wrongly."""
    try:
        with wave.open(wav_path, "rb") as w:
            return int(w.getframerate())
    except Exception:
        pass
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "default=noprint_wrappers=1:nokey=1", wav_path],
            capture_output=True, text=True, timeout=8,
        )
        val = int(res.stdout.strip())
        if val > 0:
            return val
    except Exception:
        pass
    return fallback


def generate_room_tone_pcm(duration: float, sample_rate: int = STANDARD_OUTPUT_SR) -> List[float]:
    """Generate faint -65dB stereo room-tone floor for seamless human pause stitching."""
    n_samples = max(1, int(round(duration * sample_rate)))
    rng = random.Random(42)
    amp = 0.00055  # ~ -65 dBFS
    return [rng.uniform(-amp, amp) for _ in range(n_samples)]


def apply_prosody_dsp(
    raw_wav_path: str,
    out_wav_path: str,
    atempo: float = 1.0,
    pitch_shift: float = 1.0,
    target_sr: int = STANDARD_OUTPUT_SR,
) -> bool:
    """Apply FFmpeg pitch-preserving speed adjustment & standardize to 44.1kHz stereo PCM."""
    native_sr = probe_wav_sample_rate(raw_wav_path, fallback=24000)
    filters: List[str] = []

    if abs(pitch_shift - 1.0) >= 0.008:
        shifted_sr = max(8000, int(round(native_sr * pitch_shift)))
        adj_tempo = min(1.5, max(0.65, atempo / pitch_shift))
        filters.append(f"asetrate={shifted_sr},aresample={target_sr},atempo={adj_tempo:.4f}")
    elif abs(atempo - 1.0) >= 0.01:
        filters.append(f"aresample={target_sr},atempo={min(1.5, max(0.65, atempo)):.4f}")
    else:
        filters.append(f"aresample={target_sr}")

    # Subtle 20ms smooth edge fade-in to prevent inter-segment clicks
    filters.append("afade=t=in:st=0:d=0.018")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", raw_wav_path,
        "-af", ",".join(filters),
        "-ar", str(target_sr), "-ac", "2", "-c:a", "pcm_s16le",
        out_wav_path,
    ]
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(out_wav_path) and os.path.getsize(out_wav_path) > 500


def _read_stereo_float_frames(wav_path: str) -> List[Tuple[float, float]]:
    """Read 16-bit PCM mono/stereo WAV safely using stdlib wave (zero numpy requirement)."""
    with wave.open(wav_path, "rb") as w:
        ch = w.getnchannels()
        n = w.getnframes()
        raw = w.readframes(n)
    total_vals = len(raw) // 2
    ints = struct.unpack(f"<{total_vals}h", raw[:total_vals * 2])
    if ch == 2:
        return [(ints[i] / 32768.0, ints[i + 1] / 32768.0) for i in range(0, len(ints) - 1, 2)]
    return [(v / 32768.0, v / 32768.0) for v in ints]


def _write_stereo_float_frames(wav_path: str, frames: List[Tuple[float, float]], sr: int = STANDARD_OUTPUT_SR) -> None:
    buf = bytearray()
    for l_val, r_val in frames:
        lv = int(max(-32767, min(32767, l_val * 32767.0)))
        rv = int(max(-32767, min(32767, r_val * 32767.0)))
        buf.extend(struct.pack("<hh", lv, rv))
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(buf))


def stitch_emotional_segments(
    tagged_text: str,
    tts_backend_fn: Callable[[str, Dict[str, Any], str], bool],
    out_wav: str,
    ref_bank: Optional[Dict[str, str]] = None,
    sample_rate: int = STANDARD_OUTPUT_SR,
    out_timings: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Synthesize every parsed segment with matching emotion/pause, apply DSP, and stitch cleanly."""
    segments = parse_emotion_script(tagged_text)
    if not segments:
        return False

    os.makedirs(os.path.dirname(out_wav) or ".", exist_ok=True)
    fade_samples = int(sample_rate * 0.02)
    combined_frames: List[Tuple[float, float]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, seg in enumerate(segments):
            if seg["type"] == "pause":
                noise = generate_room_tone_pcm(seg["duration"], sample_rate=sample_rate)
                combined_frames.extend((s, s) for s in noise)
                continue

            profile = dict(EMOTION_PROFILES.get(seg["emotion"], EMOTION_PROFILES["neutral"]))
            if ref_bank:
                ref_key = "suspense" if seg["emotion"] == "fear" else seg["emotion"]
                chosen_ref = ref_bank.get(ref_key) or ref_bank.get("neutral")
                if chosen_ref and os.path.exists(chosen_ref):
                    profile["ref_audio"] = chosen_ref

            raw_clip = os.path.join(tmpdir, f"seg_raw_{i}.wav")
            dsp_clip = os.path.join(tmpdir, f"seg_dsp_{i}.wav")

            ok = tts_backend_fn(seg["text"], profile, raw_clip)
            if not ok or not os.path.exists(raw_clip):
                continue

            if apply_prosody_dsp(
                raw_clip,
                dsp_clip,
                atempo=profile["atempo"],
                pitch_shift=profile["pitch_shift"],
                target_sr=sample_rate,
            ):
                active = dsp_clip
            else:
                active = raw_clip

            try:
                seg_offset_s = len(combined_frames) / float(sample_rate)
                frames = _read_stereo_float_frames(active)
                n_fr = len(frames)
                if n_fr > fade_samples * 2:
                    for k in range(fade_samples):
                        g_in = k / fade_samples
                        g_out = (fade_samples - k) / fade_samples
                        frames[k] = (frames[k][0] * g_in, frames[k][1] * g_in)
                        idx_out = n_fr - fade_samples + k
                        frames[idx_out] = (frames[idx_out][0] * g_out, frames[idx_out][1] * g_out)

                if out_timings is not None and profile.get("_word_timings"):
                    seg_dur_s = n_fr / float(sample_rate)
                    raw_frames_n = len(_read_stereo_float_frames(raw_clip)) if active != raw_clip else n_fr
                    raw_dur_s = max(0.1, raw_frames_n / float(sample_rate))
                    scale = seg_dur_s / raw_dur_s
                    for wt in profile["_word_timings"]:
                        st = seg_offset_s + float(wt.get("start", 0.0)) * scale
                        en = seg_offset_s + float(wt.get("end", 0.1)) * scale
                        out_timings.append({
                            "text": wt.get("text", ""),
                            "start": round(st, 3),
                            "end": round(max(st + 0.06, en), 3),
                        })

                combined_frames.extend(frames)
            except Exception as e:
                logger.warning(f"Failed stitching segment {i}: {e}")

    if not combined_frames:
        return False

    _write_stereo_float_frames(out_wav, combined_frames, sr=sample_rate)
    return os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000
