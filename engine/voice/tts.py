"""
engine/voice/tts.py - Multi-Engine Studio Voiceover & Word-Boundary Timing Engine
Supports:
  1. Open-Source Piper Neural TTS (hi_IN-rohan-medium / en_US-lessac-medium via HuggingFace)
  2. Edge Neural TTS (streaming WordBoundary micro-timestamps + documentary cadence)
  3. Broadcast Vocal Mastering Chain (highpass + compressor + presence EQ + dynaudnorm -> ~ -14 dB)
"""
import asyncio
import logging
import math
import os
import shutil
import struct
import subprocess
import urllib.request
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
        self.models_dir = os.path.join(config.work_dir, "piper_models")
        os.makedirs(self.voice_dir, exist_ok=True)
        os.makedirs(self.models_dir, exist_ok=True)

        self.voice_name = config.voice_settings.get("primary", "en-US-ChristopherNeural")
        self._piper_voice = None
        self._piper_checked = False

    def _ensure_piper_model(self) -> Optional[str]:
        """Download open-source Piper ONNX voice model + JSON config once and cache in workspace."""
        settings = self.config.voice_settings
        model_name = settings.get("piper_model")
        onnx_url = settings.get("piper_onnx_url")
        json_url = settings.get("piper_json_url")
        if not model_name or not onnx_url or not json_url:
            return None

        onnx_path = os.path.join(self.models_dir, f"{model_name}.onnx")
        json_path = os.path.join(self.models_dir, f"{model_name}.onnx.json")

        for url, dest in ((json_url, json_path), (onnx_url, onnx_path)):
            if not os.path.exists(dest) or os.path.getsize(dest) < 500:
                logger.info(f"Downloading open-source Piper voice asset: {os.path.basename(dest)}...")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.6"})
                    with urllib.request.urlopen(req, timeout=90) as resp, open(dest, "wb") as f:
                        while chunk := resp.read(131072):
                            f.write(chunk)
                except Exception as e:
                    logger.warning(f"Could not download Piper voice asset {dest}: {e}")
                    if os.path.exists(dest):
                        os.remove(dest)
                    return None

        if os.path.exists(onnx_path) and os.path.exists(json_path):
            return onnx_path
        return None

    def _load_piper_voice(self):
        """Lazy-load open-source PiperVoice instance across all scenes."""
        if self._piper_checked:
            return self._piper_voice
        self._piper_checked = True

        try:
            from piper import PiperVoice
        except ImportError:
            logger.debug("piper-tts python package not installed in this environment.")
            return None

        model_path = self._ensure_piper_model()
        if not model_path:
            return None

        try:
            self._piper_voice = PiperVoice.load(model_path)
            logger.info(f"✅ Loaded Open-Source Piper Neural Voice: {os.path.basename(model_path)}")
            return self._piper_voice
        except Exception as e:
            logger.warning(f"Failed to initialize PiperVoice: {e}")
            return None

    def synthesize_storyboard_narration(self, manifest: StoryboardManifest) -> StoryboardManifest:
        """Synthesize mastered voiceover for every scene, capture word timings, and sync duration."""
        logger.info(
            f"Synthesizing voiceover for {len(manifest.scenes)} scenes "
            f"(Language: {self.config.language}, Engine: {self.config.voice_engine})..."
        )

        for scene in manifest.scenes:
            clean_text = normalize_devanagari(scene.narration)
            scene.narration = clean_text
            scene.subtitle_text = clean_text

            raw_audio = os.path.join(self.voice_dir, f"voice_raw_{scene.scene_id}.wav")
            mastered_audio = os.path.join(self.voice_dir, f"voice_master_{scene.scene_id}.wav")
            aligned_audio = os.path.join(self.voice_dir, f"voice_aligned_{scene.scene_id}.wav")

            success = False
            word_timings: List[Dict[str, Any]] = []
            engine_pref = self.config.voice_engine

            # 1. Try Open-Source Piper TTS if requested or auto
            if engine_pref in ("piper", "auto"):
                success = self._generate_piper_speech(clean_text, raw_audio)

            # 2. Fallback or explicit Edge Neural TTS (also extracts WordBoundary timings)
            if not success and engine_pref in ("edge", "auto", "piper"):
                success, word_timings = self._generate_edge_speech(clean_text, raw_audio)

            # 3. Procedural fallback strictly when all network/neural engines unavailable
            if not success or not os.path.exists(raw_audio):
                logger.warning(f"Fallback speech synthesis for scene {scene.scene_id}")
                self._synthesize_procedural_speech(clean_text, raw_audio, scene.duration)

            # 4. Apply Studio Broadcast Vocal Mastering EQ + Normalization (~ -14 dB)
            self._master_voice_track(raw_audio, mastered_audio)
            active_voice = mastered_audio if os.path.exists(mastered_audio) else raw_audio

            # 5. Align spoken audio cleanly with scene duration
            spoken_dur = self._probe_duration(active_voice, fallback=scene.duration)
            tempo = self._align_audio_duration(active_voice, aligned_audio, scene.duration)

            for tmp in (raw_audio, mastered_audio):
                if tmp != aligned_audio and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

            # Build accurate word timings matched to actual spoken length
            if not word_timings:
                effective_dur = min(scene.duration, max(1.2, spoken_dur / tempo))
                word_timings = self._estimate_word_timings(clean_text, effective_dur)
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

    def _generate_piper_speech(self, text: str, output_path: str) -> bool:
        """Synthesize natural speech locally via Open-Source Piper VITS neural voice."""
        voice = self._load_piper_voice()
        if voice is None:
            return False

        try:
            try:
                from piper import SynthesisConfig
                syn_cfg = SynthesisConfig(
                    volume=1.0,
                    length_scale=1.15,
                    noise_scale=0.667,
                    noise_w_scale=0.8,
                    normalize_audio=True,
                )
                with wave.open(output_path, "wb") as wav_file:
                    voice.synthesize_wav(text, wav_file, syn_config=syn_cfg)
            except (ImportError, TypeError):
                # piper-tts 1.2.x signature fallback
                with wave.open(output_path, "wb") as wav_file:
                    voice.synthesize(text, wav_file, length_scale=1.15)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 2000:
                # Upsample Piper's native 22.05kHz mono WAV to 44.1kHz stereo PCM
                stereo_tmp = output_path + ".st.wav"
                self._convert_to_wav(output_path, stereo_tmp)
                if os.path.exists(stereo_tmp) and os.path.getsize(stereo_tmp) > 2000:
                    shutil.move(stereo_tmp, output_path)
                return True
        except Exception as e:
            logger.warning(f"Piper synthesis fallback for segment: {e}")
        return False

    def _generate_edge_speech(self, text: str, output_path: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """Generate Edge Neural speech audio and extract WordBoundary micro-timestamps."""
        mp3_temp = output_path.replace(".wav", ".mp3")
        timings: List[Dict[str, Any]] = []

        try:
            import edge_tts

            async def _stream_run():
                communicate = edge_tts.Communicate(text, self.voice_name, rate="-4%")
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

        if shutil.which("edge-tts"):
            try:
                cmd = [
                    "edge-tts",
                    "--voice", self.voice_name,
                    "--rate=-4%",
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

    def _master_voice_track(self, input_path: str, output_path: str) -> None:
        """Apply broadcast vocal EQ, gentle compression, and dynamic normalization (~ -14 dB)."""
        vocal_chain = (
            "highpass=f=85,"
            "equalizer=f=220:t=q:w=1.2:g=1.5,"
            "equalizer=f=3000:t=q:w=1.4:g=2.5,"
            "acompressor=threshold=-20dB:ratio=3:attack=5:release=100,"
            "dynaudnorm=f=150:g=11,"
            "alimiter=limit=0.92"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", vocal_chain,
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0 or not os.path.exists(output_path):
            shutil.copy2(input_path, output_path)

    @staticmethod
    def _estimate_word_timings(text: str, speech_duration: float) -> List[Dict[str, Any]]:
        """Proportional word-timing calculation mapped cleanly across spoken audio duration."""
        words = [w for w in normalize_devanagari(text).split(" ") if w]
        if not words:
            return []
        weights = [max(1, len(w)) for w in words]
        total_weight = sum(weights)
        usable_dur = max(0.8, speech_duration - 0.15)
        cursor = 0.1
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
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)

    @staticmethod
    def _probe_duration(path: str, fallback: float) -> float:
        dur_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        res = subprocess.run(dur_cmd, capture_output=True, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return fallback

    def _align_audio_duration(self, input_path: str, output_path: str, target_duration: float) -> float:
        """Smoothly tempo-adjust if slightly long, and apad with silence to match exact scene duration."""
        actual_dur = self._probe_duration(input_path, fallback=target_duration)
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
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)
        return tempo

    def _synthesize_procedural_speech(self, text: str, output_path: str, duration: float):
        """Clean synthetic narration tone strictly for offline environments missing neural engines."""
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
