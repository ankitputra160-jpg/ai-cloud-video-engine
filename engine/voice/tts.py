"""
engine/voice/tts.py - Multi-Language Narration & Word-Boundary Timing Engine
Synthesizes natural Hindi & English voiceover via Edge Neural TTS while capturing exact
word-level timestamps (WordBoundary events) for karaoke & chunked subtitles.
"""
import asyncio
import logging
import math
import os
import shutil
import struct
import subprocess
import wave
from typing import Any, Dict, List, Optional, Tuple

from engine.config import PipelineConfig
from engine.storyboard import StoryboardManifest
from engine.text.devanagari import normalize_devanagari

logger = logging.getLogger("voice.tts")


class VoiceEngine:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.voice_dir = os.path.join(config.work_dir, "voice_tracks")
        os.makedirs(self.voice_dir, exist_ok=True)
        self.voice_name = config.voice_settings.get("primary", "en-US-ChristopherNeural")

    def synthesize_storyboard_narration(self, manifest: StoryboardManifest) -> StoryboardManifest:
        """Synthesize voiceover for every scene, capture word timings, and sync duration."""
        logger.info(f"Synthesizing voiceover for {len(manifest.scenes)} scenes (Language: {self.config.language})...")

        for scene in manifest.scenes:
            clean_text = normalize_devanagari(scene.narration)
            scene.narration = clean_text
            scene.subtitle_text = clean_text

            raw_audio = os.path.join(self.voice_dir, f"voice_raw_{scene.scene_id}.wav")
            aligned_audio = os.path.join(self.voice_dir, f"voice_aligned_{scene.scene_id}.wav")

            success, word_timings = self._generate_speech_with_timings(clean_text, raw_audio)
            if not success or not os.path.exists(raw_audio):
                logger.warning(f"Fallback speech synthesis for scene {scene.scene_id}")
                self._synthesize_procedural_speech(clean_text, raw_audio, scene.duration)
                word_timings = self._estimate_word_timings(clean_text, max(1.5, scene.duration - 0.5))

            tempo = self._align_audio_duration(raw_audio, aligned_audio, scene.duration)
            if os.path.exists(raw_audio):
                try:
                    os.remove(raw_audio)
                except OSError:
                    pass

            if not word_timings:
                word_timings = self._estimate_word_timings(clean_text, max(1.5, scene.duration - 0.5))
            elif tempo != 1.0:
                word_timings = [
                    {
                        "text": wt["text"],
                        "start": round(wt["start"] / tempo, 3),
                        "end": round(wt["end"] / tempo, 3),
                    }
                    for wt in word_timings
                ]

            scene.word_timings = word_timings
            scene.voice_asset_path = aligned_audio

        return manifest

    def _generate_speech_with_timings(self, text: str, output_path: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """Generate speech audio and extract Edge-TTS WordBoundary micro-timestamps."""
        mp3_temp = output_path.replace(".wav", ".mp3")
        timings: List[Dict[str, Any]] = []

        # Primary: Python edge_tts streaming (gives both MP3 audio + WordBoundary timestamps)
        try:
            import edge_tts

            async def _stream_run():
                communicate = edge_tts.Communicate(text, self.voice_name)
                with open(mp3_temp, "wb") as audio_file:
                    async for chunk in communicate.stream():
                        ctype = chunk.get("type")
                        if ctype == "audio":
                            audio_file.write(chunk["data"])
                        elif ctype == "WordBoundary":
                            offset_s = float(chunk.get("offset", 0)) / 10_000_000.0
                            dur_s = float(chunk.get("duration", 0)) / 10_000_000.0
                            word_txt = normalize_devanagari(str(chunk.get("text", "")))
                            if word_txt:
                                timings.append({
                                    "text": word_txt,
                                    "start": round(offset_s, 3),
                                    "end": round(offset_s + max(0.08, dur_s), 3),
                                })

            asyncio.run(_stream_run())
            if os.path.exists(mp3_temp) and os.path.getsize(mp3_temp) > 500:
                self._convert_to_wav(mp3_temp, output_path)
                if os.path.exists(mp3_temp):
                    os.remove(mp3_temp)
                return True, timings
        except Exception as e:
            logger.debug(f"edge_tts stream module skipped: {e}")

        # Secondary: edge-tts CLI
        if shutil.which("edge-tts"):
            try:
                cmd = [
                    "edge-tts",
                    "--voice", self.voice_name,
                    "--text", text,
                    "--write-media", mp3_temp,
                ]
                res = subprocess.run(cmd, capture_output=True, timeout=25)
                if res.returncode == 0 and os.path.exists(mp3_temp) and os.path.getsize(mp3_temp) > 500:
                    self._convert_to_wav(mp3_temp, output_path)
                    if os.path.exists(mp3_temp):
                        os.remove(mp3_temp)
                    return True, []
            except Exception as e:
                logger.debug(f"edge-tts CLI call failed: {e}")

        return False, []

    @staticmethod
    def _estimate_word_timings(text: str, speech_duration: float) -> List[Dict[str, Any]]:
        """Proportional word-timing fallback when WordBoundary metadata is unavailable."""
        words = [w for w in normalize_devanagari(text).split(" ") if w]
        if not words:
            return []
        weights = [max(1, len(w)) for w in words]
        total_weight = sum(weights)
        usable_dur = max(0.8, speech_duration - 0.3)
        cursor = 0.15
        result: List[Dict[str, Any]] = []
        for w, wt in zip(words, weights):
            seg = usable_dur * (wt / total_weight)
            result.append({
                "text": w,
                "start": round(cursor, 3),
                "end": round(cursor + seg, 3),
            })
            cursor += seg
        return result

    def _convert_to_wav(self, input_path: str, output_path: str):
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", "44100",
            "-ac", "2",
            "-c:a", "pcm_s16le",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)

    def _align_audio_duration(self, input_path: str, output_path: str, target_duration: float) -> float:
        """Smoothly tempo-adjust if slightly long, and apad with silence to match exact scene duration."""
        dur_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]
        res = subprocess.run(dur_cmd, capture_output=True, text=True)
        try:
            actual_dur = float(res.stdout.strip())
        except Exception:
            actual_dur = target_duration

        tempo = 1.0
        filter_chain = f"apad=whole_dur={target_duration}"
        if actual_dur > target_duration and target_duration > 1.0:
            ratio = min(1.30, (actual_dur + 0.15) / target_duration)
            if ratio > 1.02:
                tempo = ratio
                filter_chain = f"atempo={tempo:.3f},apad=whole_dur={target_duration}"

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter_complex", filter_chain,
            "-t", str(target_duration),
            "-ar", "44100", "-ac", "2",
            "-c:a", "pcm_s16le",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)
        return tempo

    def _synthesize_procedural_speech(self, text: str, output_path: str, duration: float):
        """Clean synthetic narration tone to ensure offline/testing pipeline always completes."""
        sample_rate = 44100
        total_samples = int(sample_rate * max(2.0, duration - 0.5))
        samples = []
        for i in range(total_samples):
            t = i / sample_rate
            pitch = 160 + 20 * math.sin(2 * math.pi * 1.5 * t)
            envelope = ((math.sin(2 * math.pi * 3.5 * t) + 1.0) * 0.5) ** 2
            vocal = math.sin(2 * math.pi * pitch * t) * 0.25 + math.sin(2 * math.pi * (pitch * 2) * t) * 0.1
            samples.append(vocal * envelope * 0.4)

        with wave.open(output_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            raw_bytes = bytearray()
            for s in samples:
                val = int(max(-32767, min(32767, s * 32767)))
                raw_bytes.extend(struct.pack("<h", val))
            w.writeframes(raw_bytes)
