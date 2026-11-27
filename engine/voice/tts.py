"""
engine/voice/tts.py - Multi-Engine Studio Voiceover, Mood Reference Bank & Emotion Tag Router
Supports:
  1. AI4Bharat IndicF5 (Zero-Shot Flow Matching + 4-Mood Reference Bank on Colab GPU)
  2. AI4Bharat Indic Parler-TTS (Text-prompt emotion + auto-bootstraps 4 copyright-free mood clips)
  3. Qwen3-TTS 1.7B Hindi FT (optional Hinglish mode)
  4. Optional Cloud APIs: Sarvam AI (Bulbul v4) & ElevenLabs
  5. Open-Source Piper Neural TTS & Edge-TTS CPU/cloud fallbacks
  6. Broadcast Mastering (compressor + 180Hz presence EQ + loudnorm I=-14 LRA=6)
  7. Audio-First 0.001s Timing Lock + CTC Forced Alignment (MMS-300M) Speak-to-Show mapping
"""
import asyncio
import base64
import gc
import json
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
from engine.text.humanizer import strip_inline_tags
from engine.text.pronunciation import build_speak_show_alignment_spec, to_tts_tagged_text
from engine.voice.aligner import ForcedAligner
from engine.voice.emotion_router import (
    EMOTION_PROFILES,
    STANDARD_OUTPUT_SR,
    parse_emotion_script,
    stitch_emotional_segments,
)

logger = logging.getLogger("voice.tts")

AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".ogg", ".flac")
MOOD_REF_CAPTIONS: Dict[str, Tuple[str, str]] = {
    "neutral": (
        "ref_neutral.wav",
        "नमस्ते दोस्तों, आज हम एक ऐसी कहानी समझने वाले हैं जो इतिहास बदल देगी।",
    ),
    "suspense": (
        "ref_suspense.wav",
        "ज़रा रुकिए, क्योंकि असली खेल तो अभी शुरू होने वाला है।",
    ),
    "angry": (
        "ref_angry.wav",
        "आखिर इतना बड़ा सवाल इतने दिनों तक दबाया क्यों गया?",
    ),
    "fast": (
        "ref_fast.wav",
        "अचानक एक के बाद एक तीन बड़ी घटनाएँ हुईं और सब बदल गया।",
    ),
}


class VoiceEngine:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.voice_dir = os.path.join(config.work_dir, "voice_tracks")
        self.models_dir = os.path.join(config.work_dir, "piper_models")
        self.voice_bank_dir = getattr(config, "voice_bank_dir", None) or os.path.join(config.work_dir, "voice_ref")
        os.makedirs(self.voice_dir, exist_ok=True)
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.voice_bank_dir, exist_ok=True)

        self.voice_name = config.voice_settings.get("primary", "en-US-ChristopherNeural")
        self._piper_voice = None
        self._piper_checked = False
        self._indicf5_model = None
        self._indicf5_checked = False
        self._parler_model = None
        self._parler_tok = None
        self._parler_desc_tok = None
        self._parler_checked = False
        self._qwen_tts = None
        self._qwen_checked = False
        self._aligner = ForcedAligner()
        self._ref_bank: Dict[str, str] = {}
        self._ref_texts: Dict[str, str] = {}
        self._cloned_elevenlabs_voice_id: Optional[str] = None
        self._cloned_cartesia_voice_id: Optional[str] = None

    def _has_cuda_gpu(self) -> bool:
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def _prepare_custom_ref_clip(self, src_path: str, dest_wav: str, max_sec: float = 9.5) -> bool:
        """Convert any custom .mp3/.m4a/.wav sample into a denoised Dry Vocal 24kHz mono <=9.5s WAV."""
        if not src_path or not os.path.exists(src_path):
            return False
        os.makedirs(os.path.dirname(dest_wav) or ".", exist_ok=True)
        dur = self._probe_duration(src_path, fallback=0.0)
        needs_trim = dur > max_sec or not src_path.lower().endswith(".wav")
        filter_candidates = (
            "highpass=f=85,afftdn=nf=-25,silenceremove=start_periods=1:start_silence=0.15:start_threshold=-40dB",
            "highpass=f=85,silenceremove=start_periods=1:start_silence=0.15:start_threshold=-40dB",
        )
        for af in filter_candidates:
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", src_path,
                "-af", af,
                "-t", f"{max_sec:.2f}",
                "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                dest_wav,
            ]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0 and os.path.exists(dest_wav) and os.path.getsize(dest_wav) > 2000:
                return True
        if not needs_trim and src_path.lower().endswith(".wav"):
            shutil.copy2(src_path, dest_wav)
            return os.path.exists(dest_wav)
        return False

    def _auto_transcribe_ref_clip(self, wav_path: str) -> Optional[str]:
        """Optional GPU ASR (Whisper / transformers) when user supplies custom audio without a .txt transcript."""
        if not self._has_cuda_gpu():
            return None
        try:
            from transformers import pipeline as hf_pipeline
            import torch
            asr = hf_pipeline(
                "automatic-speech-recognition",
                model="openai/whisper-small",
                device=0,
                torch_dtype=torch.float16,
            )
            res = asr(wav_path, generate_kwargs={"language": "hindi" if self.config.language == "hi" else "english"})
            txt = normalize_devanagari(str((res or {}).get("text", "")).strip())
            del asr
            self._clear_gpu_cache()
            return txt or None
        except Exception as e:
            logger.debug(f"Optional ASR auto-transcript skipped: {e}")
            return None

    def _resolve_ref_transcript(self, src_path: str, prepared_wav: str, mood: str, cache_txt_path: str) -> str:
        """Resolve exact spoken words matching `prepared_wav` via config, sidecar .txt, ASR, or default."""
        explicit_txt = getattr(self.config, "voice_ref_text", None)
        if explicit_txt and explicit_txt.strip() and mood == "neutral":
            clean = normalize_devanagari(explicit_txt.strip())
            with open(cache_txt_path, "w", encoding="utf-8") as f:
                f.write(clean)
            return clean

        src_stem = os.path.splitext(src_path)[0]
        for cand in (f"{src_stem}.txt", cache_txt_path, os.path.join(self.voice_bank_dir, f"ref_{mood}.txt")):
            if cand and os.path.exists(cand):
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        raw = f.read().strip()
                    if raw:
                        return normalize_devanagari(raw)
                except OSError:
                    pass

        transcribed = self._auto_transcribe_ref_clip(prepared_wav)
        if transcribed:
            try:
                with open(cache_txt_path, "w", encoding="utf-8") as f:
                    f.write(transcribed)
            except OSError:
                pass
            return transcribed

        logger.warning(
            f"Custom voice '{os.path.basename(src_path)}' has no sidecar .txt transcript; "
            f"add '{os.path.basename(cache_txt_path)}' for maximum IndicF5 cloning fidelity."
        )
        return MOOD_REF_CAPTIONS.get(mood, MOOD_REF_CAPTIONS["neutral"])[1]

    def _discover_custom_voice_sources(self) -> Dict[str, str]:
        """Discover explicit `--voice-ref` or user audio files (.mp3/.wav/etc.) inside voice_bank_dir."""
        found: Dict[str, str] = {}
        explicit = getattr(self.config, "voice_ref_file", None)
        if explicit and os.path.exists(explicit):
            found["neutral"] = explicit

        for mood, (wav_name, _) in MOOD_REF_CAPTIONS.items():
            stem = os.path.splitext(wav_name)[0]
            for ext in AUDIO_EXTS:
                cand = os.path.join(self.voice_bank_dir, f"{stem}{ext}")
                if os.path.exists(cand) and os.path.getsize(cand) > 2000:
                    found.setdefault(mood, cand)
                    break

        if "neutral" not in found and os.path.isdir(self.voice_bank_dir):
            # Support any single custom file uploaded by the user (e.g., raju.mp3 / voice.wav)
            for fname in sorted(os.listdir(self.voice_bank_dir)):
                low = fname.lower()
                if low.endswith(AUDIO_EXTS) and not low.startswith("ref_"):
                    cand = os.path.join(self.voice_bank_dir, fname)
                    if os.path.getsize(cand) > 2000:
                        found["neutral"] = cand
                        break
        return found

    def ensure_mood_reference_bank(self) -> Dict[str, str]:
        """Load custom user voice (.mp3/.wav + .txt) cleanly, or bootstrap 4 Parler-TTS clips once."""
        existing: Dict[str, str] = {}
        ref_texts: Dict[str, str] = {}
        custom_sources = self._discover_custom_voice_sources()
        has_user_custom_voice = False

        # 1. Convert/register any user-supplied or cached clips cleanly (never mix speakers!)
        for mood, (wav_name, default_caption) in MOOD_REF_CAPTIONS.items():
            canonical_wav = os.path.join(self.voice_bank_dir, wav_name)
            txt_path = os.path.splitext(canonical_wav)[0] + ".txt"
            src = custom_sources.get(mood)

            if src:
                if os.path.abspath(src) == os.path.abspath(canonical_wav) and os.path.getsize(canonical_wav) > 4000:
                    existing[mood] = canonical_wav
                elif self._prepare_custom_ref_clip(src, canonical_wav):
                    existing[mood] = canonical_wav

                if mood in existing:
                    if os.path.exists(txt_path) or os.path.exists(os.path.splitext(src)[0] + ".txt") or not os.path.basename(src).startswith("ref_"):
                        has_user_custom_voice = True
                    # Distinguish user custom clip vs auto-bootstrapped Parler clip without .txt
                    if not os.path.basename(src).startswith("ref_") or (
                        getattr(self.config, "voice_ref_file", None) and os.path.abspath(src) == os.path.abspath(self.config.voice_ref_file)
                    ) or os.path.exists(os.path.splitext(src)[0] + ".txt"):
                        has_user_custom_voice = True
                        ref_texts[mood] = self._resolve_ref_transcript(src, existing[mood], mood, txt_path)
                    elif os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8") as f:
                            ref_texts[mood] = normalize_devanagari(f.read().strip()) or default_caption
                    else:
                        ref_texts[mood] = default_caption

        # 2. If user provided at least 1 custom clip, clone that SAME speaker across all missing moods
        #    instead of injecting Parler-TTS's different 'Tapan' voice!
        if existing and has_user_custom_voice:
            primary_mood = "neutral" if "neutral" in existing else next(iter(existing))
            for mood in MOOD_REF_CAPTIONS:
                if mood not in existing:
                    existing[mood] = existing[primary_mood]
                    ref_texts[mood] = ref_texts.get(primary_mood, "")
            self._ref_bank = existing
            self._ref_texts = ref_texts
            return existing

        missing = [m for m in MOOD_REF_CAPTIONS if m not in existing]
        if missing and self._has_cuda_gpu() and self._load_indic_parler():
            logger.info(f"Bootstrapping {len(missing)} studio reference clips in {self.voice_bank_dir}...")
            for mood in missing:
                fname, sample_hi = MOOD_REF_CAPTIONS[mood]
                out_wav = os.path.join(self.voice_bank_dir, fname)
                txt_path = os.path.splitext(out_wav)[0] + ".txt"
                profile_key = "fear" if mood == "suspense" else ("angry" if mood == "angry" else ("fast" if mood == "fast" else "neutral"))
                caption = EMOTION_PROFILES[profile_key]["parler_caption"]
                raw_tmp = out_wav + ".raw.wav"
                if self._synthesize_parler_clip(sample_hi, caption, raw_tmp):
                    self._master_voice_track(raw_tmp, out_wav)
                    if os.path.exists(raw_tmp):
                        os.remove(raw_tmp)
                    if os.path.exists(out_wav) and os.path.getsize(out_wav) > 4000:
                        existing[mood] = out_wav
                        ref_texts[mood] = sample_hi
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(sample_hi)
            if self.config.voice_engine in ("auto", "indicf5", "qwen3_tts"):
                self._unload_parler()

        self._ref_bank = existing
        self._ref_texts = ref_texts
        return existing

    def _load_indicf5(self) -> bool:
        if self._indicf5_checked:
            return self._indicf5_model is not None
        self._indicf5_checked = True
        if not self._has_cuda_gpu():
            return False
        try:
            import torch
            from transformers import AutoModel
            hf_tok = getattr(self.config, "hf_token", None) or os.environ.get("HF_TOKEN", "").strip() or None
            if hf_tok:
                os.environ["HF_TOKEN"] = hf_tok
            logger.info("Loading AI4Bharat IndicF5 neural voice engine...")
            self._indicf5_model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
            self._indicf5_model.to("cuda")
            return True
        except Exception as e:
            logger.debug(f"IndicF5 unavailable cleanly: {e}")
            return False

    def _load_indic_parler(self) -> bool:
        if self._parler_checked:
            return self._parler_model is not None
        self._parler_checked = True
        if not self._has_cuda_gpu():
            return False
        try:
            import torch
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer
            hf_tok = getattr(self.config, "hf_token", None) or os.environ.get("HF_TOKEN", "").strip() or None
            if hf_tok:
                os.environ["HF_TOKEN"] = hf_tok
            repo = "ai4bharat/indic-parler-tts"
            logger.info("Loading AI4Bharat Indic Parler-TTS...")
            self._parler_model = ParlerTTSForConditionalGeneration.from_pretrained(repo).to("cuda")
            self._parler_tok = AutoTokenizer.from_pretrained(repo)
            self._parler_desc_tok = AutoTokenizer.from_pretrained(self._parler_model.config.text_encoder._name_or_path)
            return True
        except Exception as e:
            logger.debug(f"Indic Parler-TTS unavailable cleanly: {e}")
            return False

    def _load_qwen_tts(self) -> bool:
        if self._qwen_checked:
            return self._qwen_tts is not None
        self._qwen_checked = True
        if not self._has_cuda_gpu():
            return False
        try:
            from qwen_tts import Qwen3TTSModel
            import torch
            logger.info("Loading Qwen3-TTS Hindi FT model...")
            self._qwen_tts = Qwen3TTSModel.from_pretrained(
                "saumilyajj/Qwen3-TTS-12Hz-1.7B-Base-hindi-ft",
                device_map="cuda:0",
                dtype=torch.bfloat16,
            )
            return True
        except Exception as e:
            logger.debug(f"Qwen3-TTS unavailable cleanly: {e}")
            return False

    def _unload_parler(self) -> None:
        for attr in ("_parler_model", "_parler_tok", "_parler_desc_tok"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    del obj
                except Exception:
                    pass
                setattr(self, attr, None)
        self._parler_checked = False
        self._clear_gpu_cache()

    def unload_all_tts(self) -> None:
        """Unload GPU TTS models cleanly before CTC alignment / visual stages."""
        for attr in ("_indicf5_model", "_qwen_tts"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    del obj
                except Exception:
                    pass
                setattr(self, attr, None)
        self._indicf5_checked = False
        self._qwen_checked = False
        self._unload_parler()

    @staticmethod
    def _clear_gpu_cache() -> None:
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _synthesize_indicf5_clip(self, text: str, ref_audio_path: str, ref_text: str, out_wav: str, seed: int = 2026) -> bool:
        if not self._load_indicf5():
            return False
        if not ref_audio_path or not os.path.exists(ref_audio_path):
            return False
        try:
            import numpy as np
            import soundfile as sf
            import torch
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            clean_txt = normalize_devanagari(text)
            audio = self._indicf5_model(
                clean_txt,
                ref_audio_path=ref_audio_path,
                ref_text=ref_text,
            )
            if getattr(audio, "dtype", None) == np.int16:
                audio = audio.astype(np.float32) / 32768.0
            sf.write(out_wav, np.array(audio, dtype=np.float32), samplerate=24000)
            return os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000
        except Exception as e:
            logger.warning(f"IndicF5 synthesis failed: {e}")
            return False

    def _synthesize_parler_clip(self, text: str, caption: str, out_wav: str, seed: int = 2026) -> bool:
        if not self._load_indic_parler():
            return False
        try:
            import soundfile as sf
            import torch
            torch.manual_seed(seed)
            desc_in = self._parler_desc_tok(caption, return_tensors="pt").to("cuda")
            prompt_in = self._parler_tok(normalize_devanagari(text), return_tensors="pt").to("cuda")
            gen = self._parler_model.generate(
                input_ids=desc_in.input_ids,
                attention_mask=desc_in.attention_mask,
                prompt_input_ids=prompt_in.input_ids,
                prompt_attention_mask=prompt_in.attention_mask,
            )
            audio_arr = gen.cpu().numpy().squeeze()
            sf.write(out_wav, audio_arr, self._parler_model.config.sampling_rate)
            return os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000
        except Exception as e:
            logger.warning(f"Parler-TTS synthesis failed: {e}")
            return False

    def _synthesize_qwen_clip(
        self, text: str, ref_audio_path: Optional[str], out_wav: str, seed: int = 2026, ref_text: Optional[str] = None
    ) -> bool:
        if not ref_audio_path or not os.path.exists(ref_audio_path):
            return False
        if not self._load_qwen_tts():
            return False
        try:
            import soundfile as sf
            import torch
            torch.manual_seed(seed)
            resolved_ref_text = (ref_text or self._ref_texts.get("neutral") or MOOD_REF_CAPTIONS["neutral"][1]).strip()
            kwargs: Dict[str, Any] = {
                "text": text,
                "language": "Auto",
                "temperature": 0.6,
                "repetition_penalty": 1.15,
                "ref_audio": ref_audio_path,
                "ref_text": resolved_ref_text,
            }
            wavs, sr = self._qwen_tts.generate_voice_clone(**kwargs)
            sf.write(out_wav, wavs[0], sr)
            return os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000
        except Exception as e:
            logger.warning(f"Qwen3-TTS synthesis failed: {e}")
            return False

    @staticmethod
    def _pack_msgpack(obj: Any) -> bytes:
        """Pure-Python MessagePack serializer (supports Fish Audio inline zero-shot `references` without extra deps)."""
        try:
            import ormsgpack
            return ormsgpack.packb(obj)
        except ImportError:
            pass

        out = bytearray()

        def _pack_item(v: Any) -> None:
            if v is None:
                out.append(0xC0)
            elif isinstance(v, bool):
                out.append(0xC3 if v else 0xC2)
            elif isinstance(v, int):
                if 0 <= v <= 0x7F:
                    out.append(v)
                elif -32 <= v < 0:
                    out.append(v & 0xFF)
                elif 0 <= v <= 0xFFFFFFFF:
                    out.append(0xCE)
                    out.extend(struct.pack(">I", v))
                else:
                    out.append(0xD3)
                    out.extend(struct.pack(">q", v))
            elif isinstance(v, float):
                out.append(0xCB)
                out.extend(struct.pack(">d", v))
            elif isinstance(v, (bytes, bytearray)):
                n = len(v)
                if n <= 0xFF:
                    out.extend(b"\xC4" + struct.pack("B", n))
                elif n <= 0xFFFF:
                    out.extend(b"\xC5" + struct.pack(">H", n))
                else:
                    out.extend(b"\xC6" + struct.pack(">I", n))
                out.extend(v)
            elif isinstance(v, str):
                b = v.encode("utf-8")
                n = len(b)
                if n <= 31:
                    out.append(0xA0 | n)
                elif n <= 0xFF:
                    out.extend(b"\xD9" + struct.pack("B", n))
                elif n <= 0xFFFF:
                    out.extend(b"\xDA" + struct.pack(">H", n))
                else:
                    out.extend(b"\xDB" + struct.pack(">I", n))
                out.extend(b)
            elif isinstance(v, (list, tuple)):
                n = len(v)
                if n <= 15:
                    out.append(0x90 | n)
                elif n <= 0xFFFF:
                    out.extend(b"\xDC" + struct.pack(">H", n))
                else:
                    out.extend(b"\xDD" + struct.pack(">I", n))
                for elem in v:
                    _pack_item(elem)
            elif isinstance(v, dict):
                n = len(v)
                if n <= 15:
                    out.append(0x80 | n)
                elif n <= 0xFFFF:
                    out.extend(b"\xDE" + struct.pack(">H", n))
                else:
                    out.extend(b"\xDF" + struct.pack(">I", n))
                for k, val in v.items():
                    _pack_item(str(k) if not isinstance(k, (str, bytes, int)) else k)
                    _pack_item(val)
            else:
                _pack_item(str(v))

        _pack_item(obj)
        return bytes(out)

    @staticmethod
    def _build_multipart_form(
        fields: List[Tuple[str, str]],
        file_field: str,
        file_path: str,
    ) -> Tuple[bytes, str]:
        """Build standard multipart/form-data payload cleanly for voice cloning REST APIs."""
        boundary = "----AIDocEngineBoundary7f3a9c"
        filename = os.path.basename(file_path)
        mime = "audio/wav" if filename.lower().endswith(".wav") else "audio/mpeg"
        with open(file_path, "rb") as f:
            audio_bytes = f.read()
        body = bytearray()
        for fname, val in fields:
            body.extend(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{fname}\"\r\n\r\n{val}\r\n".encode("utf-8")
            )
        body.extend(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
        )
        body.extend(audio_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        return bytes(body), f"multipart/form-data; boundary={boundary}"

    def _save_audio_bytes_to_wav(self, audio_bytes: bytes, suffix: str, out_wav: str) -> bool:
        if not audio_bytes or len(audio_bytes) < 400:
            return False
        tmp = f"{out_wav}{suffix}"
        try:
            with open(tmp, "wb") as f:
                f.write(audio_bytes)
            self._convert_to_wav(tmp, out_wav)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000

    def _generate_sarvam_speech(self, text: str, out_wav: str, emotion: str = "neutral") -> bool:
        api_key = getattr(self.config, "sarvam_api_key", None) or os.environ.get("SARVAM_API_KEY", "").strip()
        if not api_key:
            return False
        pace_map = {"fear": 0.90, "slow": 0.88, "angry": 1.06, "fast": 1.12, "neutral": 0.98}
        lang_code = "hi-IN" if self.config.language == "hi" else "en-IN"
        is_fem = "female" in self.voice_name.lower()
        try:
            # Official Sarvam Bulbul v3 REST schema
            body = {
                "text": text[:2400],
                "language_code": lang_code,
                "model": "bulbul:v3",
                "speaker": "simran" if is_fem else "shubh",
                "pace": pace_map.get(emotion, 0.98),
                "speech_sample_rate": 24000,
                "enable_preprocessing": True,
            }
            req = urllib.request.Request(
                "https://api.sarvam.ai/text-to-speech",
                data=json.dumps(body).encode("utf-8"),
                headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                audios = data.get("audios") or []
                if audios:
                    return self._save_audio_bytes_to_wav(base64.b64decode(audios[0]), ".sarvam.wav", out_wav)
        except Exception as e:
            logger.debug(f"Sarvam AI TTS skipped: {e}")
        return False

    def _generate_fish_speech(
        self, text: str, out_wav: str, ref_audio_path: Optional[str] = None, ref_text: str = ""
    ) -> bool:
        """Synthesize expressive or zero-shot cloned speech via Fish Audio REST API (S2.1 Pro)."""
        api_key = getattr(self.config, "fish_api_key", None) or os.environ.get("FISH_API_KEY", "").strip()
        if not api_key:
            return False
        ref_id = getattr(self.config, "fish_reference_id", None) or os.environ.get("FISH_REFERENCE_ID", "").strip()
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "model": "s2.1-pro",
        }
        try:
            if ref_id:
                payload: Dict[str, Any] = {"text": text, "reference_id": ref_id, "format": "wav"}
                raw_body = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
            elif ref_audio_path and os.path.exists(ref_audio_path):
                with open(ref_audio_path, "rb") as f:
                    ref_bytes = f.read()
                payload = {
                    "text": text,
                    "format": "wav",
                    "references": [{"audio": ref_bytes, "text": ref_text or MOOD_REF_CAPTIONS["neutral"][1]}],
                }
                raw_body = self._pack_msgpack(payload)
                headers["Content-Type"] = "application/msgpack"
            else:
                payload = {"text": text, "format": "wav"}
                raw_body = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"

            req = urllib.request.Request("https://api.fish.audio/v1/tts", data=raw_body, headers=headers)
            with urllib.request.urlopen(req, timeout=35) as resp:
                return self._save_audio_bytes_to_wav(resp.read(), ".fish.wav", out_wav)
        except Exception as e:
            logger.debug(f"Fish Audio TTS skipped cleanly: {e}")
        return False

    def _clone_cartesia_voice(self, api_key: str, sample_audio_path: str, name: str = "AIDocCartesiaVoice") -> Optional[str]:
        """Instant-clone custom reference clip via Cartesia POST /voices/clone once per run."""
        if self._cloned_cartesia_voice_id:
            return self._cloned_cartesia_voice_id
        if not api_key or not sample_audio_path or not os.path.exists(sample_audio_path):
            return None
        try:
            body, ctype = self._build_multipart_form(
                [("name", name), ("description", "Documentary voice clone"), ("access", "private")],
                file_field="clip",
                file_path=sample_audio_path,
            )
            req = urllib.request.Request(
                "https://api.cartesia.ai/voices/clone",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Cartesia-Version": "2026-08-14",
                    "Content-Type": ctype,
                },
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                vid = payload.get("id")
                if vid:
                    self._cloned_cartesia_voice_id = str(vid)
                    logger.info(f"✅ Cartesia Instant Voice Clone ready (voice_id={vid})")
                    return self._cloned_cartesia_voice_id
        except Exception as e:
            logger.warning(f"Cartesia voice cloning skipped cleanly: {e}")
        return None

    def _generate_cartesia_speech(self, text: str, out_wav: str, ref_audio_path: Optional[str] = None) -> bool:
        """Synthesize crisp zero-shot cloned Hindi/English audio via Cartesia Sonic REST API."""
        api_key = getattr(self.config, "cartesia_api_key", None) or os.environ.get("CARTESIA_API_KEY", "").strip()
        if not api_key:
            return False
        voice_id = (
            getattr(self.config, "cartesia_voice_id", None)
            or os.environ.get("CARTESIA_VOICE_ID", "").strip()
            or self._cloned_cartesia_voice_id
        )
        if not voice_id and ref_audio_path and os.path.exists(ref_audio_path):
            voice_id = self._clone_cartesia_voice(api_key, ref_audio_path)
        if not voice_id:
            return False
        try:
            body = {
                "model_id": "sonic-3.6",
                "transcript": text,
                "language": "hi" if self.config.language == "hi" else "en",
                "voice": {"mode": "id", "id": voice_id},
                "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100},
            }
            req = urllib.request.Request(
                "https://api.cartesia.ai/tts/bytes",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Cartesia-Version": "2026-08-14",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return self._save_audio_bytes_to_wav(resp.read(), ".cartesia.wav", out_wav)
        except Exception as e:
            logger.debug(f"Cartesia TTS skipped cleanly: {e}")
        return False

    def _clone_elevenlabs_voice(self, api_key: str, sample_audio_path: str, name: str = "AIDocCustomVoice") -> Optional[str]:
        """Instant-clone a local voice sample via ElevenLabs /v1/voices/add once per run."""
        if self._cloned_elevenlabs_voice_id:
            return self._cloned_elevenlabs_voice_id
        if not api_key or not sample_audio_path or not os.path.exists(sample_audio_path):
            return None
        try:
            body, ctype = self._build_multipart_form(
                [("name", name), ("description", "Documentary narrator reference clone")],
                file_field="files",
                file_path=sample_audio_path,
            )
            req = urllib.request.Request(
                "https://api.elevenlabs.io/v1/voices/add",
                data=body,
                headers={"xi-api-key": api_key, "Content-Type": ctype},
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                vid = payload.get("voice_id")
                if vid:
                    self._cloned_elevenlabs_voice_id = str(vid)
                    logger.info(f"✅ ElevenLabs Instant Voice Clone ready (voice_id={vid})")
                    return self._cloned_elevenlabs_voice_id
        except Exception as e:
            logger.warning(f"ElevenLabs instant voice cloning skipped cleanly: {e}")
        return None

    def _resolve_elevenlabs_voice_id(self, api_key: str) -> str:
        explicit = (
            getattr(self.config, "elevenlabs_voice_id", None)
            or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        )
        if explicit:
            return explicit
        if self._cloned_elevenlabs_voice_id:
            return self._cloned_elevenlabs_voice_id
        custom_sources = self._discover_custom_voice_sources()
        sample = self._ref_bank.get("neutral") or custom_sources.get("neutral")
        if sample and os.path.exists(sample):
            cloned = self._clone_elevenlabs_voice(api_key, sample)
            if cloned:
                return cloned
        return "pNInz6obpgDQGcFmaJgB"

    def _generate_elevenlabs_speech(self, text: str, out_wav: str) -> bool:
        api_key = getattr(self.config, "elevenlabs_api_key", None) or os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not api_key:
            return False
        voice_id = self._resolve_elevenlabs_voice_id(api_key)
        try:
            body = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.78, "style": 0.35},
            }
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                data=json.dumps(body).encode("utf-8"),
                headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return self._save_audio_bytes_to_wav(resp.read(), ".el.mp3", out_wav)
        except Exception as e:
            logger.debug(f"ElevenLabs TTS skipped: {e}")
        return False

    def synthesize_storyboard_narration(
        self, manifest: StoryboardManifest, lock_audio_first: bool = True
    ) -> StoryboardManifest:
        """Synthesize expressive emotion-routed voiceover, master audio (-14 LUFS LRA=6),
        lock exact scene.duration to 0.001s (Zero Frame Drift), and run CTC forced alignment."""
        logger.info(
            f"Synthesizing voiceover for {len(manifest.scenes)} scenes "
            f"(Language: {self.config.language}, Engine: {self.config.voice_engine})..."
        )
        engine_pref = self.config.voice_engine
        has_gpu = self._has_cuda_gpu()
        fps = self.config.profile.fps

        if (has_gpu and engine_pref in ("auto", "indicf5", "qwen3_tts")) or getattr(self.config, "voice_ref_file", None) or self._discover_custom_voice_sources():
            self.ensure_mood_reference_bank()

        clean_voice_paths: Dict[str, str] = {}
        scene_edge_timings: Dict[str, List[Dict[str, Any]]] = {}

        # Pass 1: Synthesize + Master every scene audio track cleanly
        for idx, scene in enumerate(manifest.scenes):
            mastered_audio = os.path.join(self.voice_dir, f"voice_aligned_{scene.scene_id}.wav")
            clean_voice_paths[scene.scene_id] = mastered_audio

            # Checkpoint resume hit: ALWAYS prefer clean voice_aligned_*.wav (never mixed BGM+SFX!)
            if os.path.exists(mastered_audio) and os.path.getsize(mastered_audio) > 4000:
                exact_dur = self._probe_duration(mastered_audio, fallback=scene.duration)
                if lock_audio_first and exact_dur > 0.5:
                    scene.duration = round(max(1.0, round(exact_dur * fps) / fps), 3)
                if not getattr(scene, "voice_asset_path", None) or not os.path.exists(scene.voice_asset_path):
                    scene.voice_asset_path = mastered_audio
                continue

            if getattr(scene, "voice_asset_path", None) and os.path.exists(scene.voice_asset_path) and os.path.getsize(scene.voice_asset_path) > 4000:
                exact_dur = self._probe_duration(scene.voice_asset_path, fallback=scene.duration)
                if lock_audio_first and exact_dur > 0.5:
                    scene.duration = round(max(1.0, round(exact_dur * fps) / fps), 3)
                continue

            tagged = getattr(scene, "tts_text", "") or getattr(scene, "tagged_narration", "") or scene.narration
            if self.config.language == "hi":
                tagged = to_tts_tagged_text(tagged)

            clean_display = normalize_devanagari(scene.subtitle_text or scene.narration)
            scene.narration = clean_display
            scene.subtitle_text = clean_display

            # Populate Speak/Show spans if missing (e.g., curated storyboard JSON)
            if not getattr(scene, "speak_words", None) or not getattr(scene, "display_spans", None):
                if self.config.language == "hi":
                    spec = build_speak_show_alignment_spec(scene.tagged_narration or clean_display)
                    scene.speak_words = spec["speak_words"]
                    scene.display_spans = spec["display_spans"]
                else:
                    scene.speak_words = [w for w in strip_inline_tags(clean_display).split() if w]
                    scene.display_spans = [
                        {"span_id": f"span_{i+1}", "show": w, "speak_start_idx": i, "speak_end_idx": i}
                        for i, w in enumerate(scene.speak_words)
                    ]

            raw_audio = os.path.join(self.voice_dir, f"voice_raw_{scene.scene_id}.wav")
            stitched_edge_timings: List[Dict[str, Any]] = []
            success = False

            def _backend_synthesize(seg_text: str, profile: Dict[str, Any], seg_wav: str) -> bool:
                ref_file = profile.get("ref_audio")
                ref_mood_key = "suspense" if "suspense" in str(ref_file) else ("angry" if "angry" in str(ref_file) else ("fast" if "fast" in str(ref_file) else "neutral"))
                ref_transcript = (
                    self._ref_texts.get(ref_mood_key)
                    or self._ref_texts.get("neutral")
                    or MOOD_REF_CAPTIONS.get(ref_mood_key, MOOD_REF_CAPTIONS["neutral"])[1]
                )
                r_path = ref_file if (ref_file and os.path.exists(ref_file)) else self._ref_bank.get("neutral", "")

                # Valid Multi-Provider Waterfall (preferred engine first, graceful cascade on failure/quota)
                default_chain = ["fish", "sarvam", "cartesia", "elevenlabs", "indicf5", "qwen3_tts", "indic_parler", "piper", "edge"]
                order = [engine_pref] + [p for p in default_chain if p != engine_pref] if engine_pref in default_chain else default_chain

                for provider in order:
                    if provider == "fish" and getattr(self.config, "fish_api_key", None):
                        if self._generate_fish_speech(seg_text, seg_wav, ref_audio_path=r_path, ref_text=ref_transcript):
                            return True
                    elif provider == "sarvam" and getattr(self.config, "sarvam_api_key", None):
                        if self._generate_sarvam_speech(seg_text, seg_wav, emotion=ref_mood_key):
                            return True
                    elif provider == "cartesia" and getattr(self.config, "cartesia_api_key", None):
                        if self._generate_cartesia_speech(seg_text, seg_wav, ref_audio_path=r_path):
                            return True
                    elif provider == "elevenlabs" and getattr(self.config, "elevenlabs_api_key", None):
                        if self._generate_elevenlabs_speech(seg_text, seg_wav):
                            return True
                    elif provider == "indicf5" and has_gpu and self._ref_bank:
                        if self._synthesize_indicf5_clip(seg_text, r_path, ref_transcript, seg_wav, seed=2026):
                            return True
                    elif provider == "qwen3_tts" and has_gpu and self._ref_bank:
                        if self._synthesize_qwen_clip(seg_text, r_path, seg_wav, seed=2026, ref_text=ref_transcript):
                            return True
                    elif provider == "indic_parler" and has_gpu:
                        if self._synthesize_parler_clip(seg_text, profile["parler_caption"], seg_wav, seed=2026):
                            return True
                    elif provider == "piper":
                        if self._generate_piper_speech(seg_text, seg_wav):
                            return True
                    elif provider == "edge":
                        ok_edge, wt = self._generate_edge_speech(seg_text, seg_wav)
                        if ok_edge:
                            if wt:
                                profile["_word_timings"] = wt
                            return True
                return False

            # Run Emotion Tag Router if inline tags or GPU TTS present, else direct clean call
            if parse_emotion_script(tagged):
                success = stitch_emotional_segments(
                    tagged,
                    tts_backend_fn=_backend_synthesize,
                    out_wav=raw_audio,
                    ref_bank=self._ref_bank,
                    sample_rate=STANDARD_OUTPUT_SR,
                    out_timings=stitched_edge_timings,
                )
            if stitched_edge_timings:
                scene_edge_timings[scene.scene_id] = stitched_edge_timings

            if not success or not os.path.exists(raw_audio):
                logger.warning(f"Fallback speech synthesis for scene {scene.scene_id}")
                self._synthesize_procedural_speech(clean_display, raw_audio, scene.duration)

            self._master_voice_track(raw_audio, mastered_audio)
            if os.path.exists(raw_audio) and raw_audio != mastered_audio:
                try:
                    os.remove(raw_audio)
                except OSError:
                    pass

            actual_dur = self._probe_duration(mastered_audio, fallback=scene.duration)
            if lock_audio_first and actual_dur > 0.6:
                # Audio-First Timing Lock: align scene duration strictly to frame boundary (0.001s exact)
                frame_locked_dur = round(max(1.2, round(actual_dur * fps) / fps), 3)
                if abs(frame_locked_dur - actual_dur) > 0.005:
                    padded = mastered_audio + ".pad.wav"
                    self._pad_exact_duration(mastered_audio, padded, frame_locked_dur)
                    if os.path.exists(padded):
                        shutil.move(padded, mastered_audio)
                scene.duration = frame_locked_dur
                # Rescale visual_beats proportionally to sum exactly to new scene.duration
                self._rescale_visual_beats(scene, frame_locked_dur)
            else:
                padded = mastered_audio + ".pad.wav"
                self._align_audio_duration(mastered_audio, padded, scene.duration)
                if os.path.exists(padded):
                    shutil.move(padded, mastered_audio)

            scene.voice_asset_path = mastered_audio

            # Periodic CUDA cache clearing to stop VRAM fragmentation over 25-min runs
            if has_gpu and (idx + 1) % 25 == 0:
                self._clear_gpu_cache()

        # Unload all TTS models cleanly before running MMS-300M CTC alignment
        self.unload_all_tts()

        # Pass 2: CTC Forced Alignment (MMS-300M) or real Edge-TTS WordBoundary sync -> Speak-to-Show Mapping
        use_ctc = self._aligner.is_ctc_available()
        for scene in manifest.scenes:
            # Always align against clean isolated voice track, never BGM+SFX mixed track
            clean_wav = clean_voice_paths.get(scene.scene_id)
            align_audio = clean_wav if (clean_wav and os.path.exists(clean_wav)) else scene.voice_asset_path
            if not align_audio or not os.path.exists(align_audio):
                continue

            words_to_align = scene.speak_words or scene.narration.split()
            edge_wt = scene_edge_timings.get(scene.scene_id)
            if (not use_ctc) and edge_wt:
                speak_timings = ForcedAligner.align_with_word_boundaries(
                    words_to_align, edge_wt, audio_duration=scene.duration
                )
            else:
                speak_timings = self._aligner.align_speak_words(
                    align_audio,
                    words_to_align,
                    audio_duration=scene.duration,
                    language="hin" if self.config.language == "hi" else "eng",
                )

            if scene.display_spans and self.config.language == "hi":
                scene.word_timings = ForcedAligner.map_speak_timings_to_show_spans(
                    speak_timings,
                    scene.display_spans,
                    audio_duration=scene.duration,
                )
            else:
                scene.word_timings = speak_timings

        self._aligner.unload()
        return manifest

    @staticmethod
    def _rescale_visual_beats(scene, exact_duration: float) -> None:
        beats = getattr(scene, "visual_beats", None)
        if not beats:
            return
        old_sum = sum(float(b.get("duration", 0.0)) for b in beats) or exact_duration
        ratio = exact_duration / old_sum
        running = 0.0
        for idx, b in enumerate(beats):
            if idx == len(beats) - 1:
                b["duration"] = round(max(0.5, exact_duration - running), 3)
            else:
                d = round(max(0.5, float(b.get("duration", 3.5)) * ratio), 3)
                b["duration"] = d
                running += d

    def _ensure_piper_model(self) -> Optional[str]:
        """Download open-source Piper ONNX voice model + JSON config once and cache."""
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
                    req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/3.0"})
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
        if self._piper_checked:
            return self._piper_voice
        self._piper_checked = True
        try:
            from piper import PiperVoice
        except ImportError:
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

    def _generate_piper_speech(self, text: str, output_path: str) -> bool:
        voice = self._load_piper_voice()
        if voice is None:
            return False
        try:
            try:
                from piper import SynthesisConfig
                syn_cfg = SynthesisConfig(volume=1.0, length_scale=1.12, noise_scale=0.667, noise_w_scale=0.8, normalize_audio=True)
                with wave.open(output_path, "wb") as wav_file:
                    voice.synthesize_wav(text, wav_file, syn_config=syn_cfg)
            except (ImportError, TypeError):
                with wave.open(output_path, "wb") as wav_file:
                    voice.synthesize(text, wav_file, length_scale=1.12)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 2000:
                stereo_tmp = output_path + ".st.wav"
                self._convert_to_wav(output_path, stereo_tmp)
                if os.path.exists(stereo_tmp) and os.path.getsize(stereo_tmp) > 2000:
                    shutil.move(stereo_tmp, output_path)
                return True
        except Exception as e:
            logger.warning(f"Piper synthesis fallback: {e}")
        return False

    def _generate_edge_speech(self, text: str, output_path: str) -> Tuple[bool, List[Dict[str, Any]]]:
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
                cmd = ["edge-tts", "--voice", self.voice_name, "--rate=-4%", "--text", text, "--write-media", mp3_temp]
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
        """Apply broadcast compressor + 180Hz vocal warmth + steady LRA=6 loudness normalization."""
        vocal_chain = (
            "highpass=f=85,"
            "equalizer=f=180:width_type=h:width=100:g=2,"
            "equalizer=f=3000:t=q:w=1.4:g=2.0,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,"
            "loudnorm=I=-14:TP=-1.5:LRA=6,"
            "alimiter=limit=0.92"
        )
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-af", vocal_chain,
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0 or not os.path.exists(output_path):
            shutil.copy2(input_path, output_path)

    def _pad_exact_duration(self, input_path: str, output_path: str, exact_duration: float) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-af", f"apad=whole_dur={exact_duration:.3f}",
            "-t", f"{exact_duration:.3f}",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0 or not os.path.exists(output_path):
            shutil.copy2(input_path, output_path)

    @staticmethod
    def _estimate_word_timings(text: str, speech_duration: float) -> List[Dict[str, Any]]:
        words = [w for w in normalize_devanagari(text).split(" ") if w]
        return ForcedAligner.estimate_proportional_timings(words, speech_duration)

    def _convert_to_wav(self, input_path: str, output_path: str):
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
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
        actual_dur = self._probe_duration(input_path, fallback=target_duration)
        tempo = 1.0
        filter_chain = f"apad=whole_dur={target_duration}"
        if actual_dur > target_duration and target_duration > 1.0:
            ratio = min(1.30, (actual_dur + 0.15) / target_duration)
            if ratio > 1.02:
                tempo = ratio
                filter_chain = f"atempo={tempo:.3f},apad=whole_dur={target_duration}"

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-filter_complex", filter_chain,
            "-t", str(target_duration),
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)
        return tempo

    def _synthesize_procedural_speech(self, text: str, output_path: str, duration: float):
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
