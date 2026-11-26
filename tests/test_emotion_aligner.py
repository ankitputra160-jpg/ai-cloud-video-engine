"""
tests/test_emotion_aligner.py - Phase 3 Tests for Emotion Tag Router, Sample-Rate Safe DSP,
CTC Speak-to-Show Span Alignment, Atomic Subtitle Span-ID Locking, Foley SFX & Sidechain Mixer.
"""
import math
import os
import struct
import tempfile
import unittest
import wave

from engine.audio.bgm import BackgroundMusicEngine
from engine.audio.mixer import AudioProductionMixer
from engine.audio.sfx import SoundEffectsEngine, resolve_sfx_clip
from engine.storyboard import SceneDefinition, StoryboardManifest
from engine.text.pronunciation import build_speak_show_alignment_spec
from engine.voice.aligner import ForcedAligner
from engine.voice.emotion_router import (
    apply_prosody_dsp,
    parse_emotion_script,
    probe_wav_sample_rate,
    stitch_emotional_segments,
)
from engine.voice.subtitles import SubtitleGenerator


def _write_test_sine_wav(path: str, sr: int = 24000, duration: float = 0.8, freq: float = 220.0):
    n = int(sr * duration)
    buf = bytearray()
    for i in range(n):
        val = int(0.35 * math.sin(2 * math.pi * freq * (i / sr)) * 32767)
        buf.extend(struct.pack("<h", val))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(buf))


class TestEmotionAndAligner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmp)

    def test_emotion_tag_parsing_and_shift_guard(self):
        tagged = (
            "[fear]ज़रा रुकिए, ये सामान्य मामला नहीं है।[/fear] "
            "[pause:0.5s] "
            "[angry]आखिर डेटा किसने छुपाया?[/angry] "
            "[fast]और यहाँ तीसरा बदलाव शांत होना चाहिए।[/fast]"
        )
        segs = parse_emotion_script(tagged, max_emotion_shifts=2)
        self.assertEqual(len(segs), 4)
        self.assertEqual(segs[0]["emotion"], "fear")
        self.assertEqual(segs[1], {"type": "pause", "duration": 0.5})
        self.assertEqual(segs[2]["emotion"], "angry")
        # 3rd shift clamped back to 'neutral' for vocal stability
        self.assertEqual(segs[3]["emotion"], "neutral")

    def test_sample_rate_safe_dsp_and_stitching(self):
        wav24 = os.path.join(self.tmp, "clip24.wav")
        wav44 = os.path.join(self.tmp, "clip44.wav")
        _write_test_sine_wav(wav24, sr=24000, duration=0.8)
        _write_test_sine_wav(wav44, sr=44100, duration=0.8)

        self.assertEqual(probe_wav_sample_rate(wav24), 24000)
        self.assertEqual(probe_wav_sample_rate(wav44), 44100)

        out24 = os.path.join(self.tmp, "dsp24.wav")
        out44 = os.path.join(self.tmp, "dsp44.wav")
        self.assertTrue(apply_prosody_dsp(wav24, out24, atempo=0.90, pitch_shift=0.96))
        self.assertTrue(apply_prosody_dsp(wav44, out44, atempo=1.10, pitch_shift=1.02))
        self.assertEqual(probe_wav_sample_rate(out24), 44100)
        self.assertEqual(probe_wav_sample_rate(out44), 44100)

        # Stitch full speech + pause + speech workflow cleanly
        def _fake_backend(txt, profile, save_path):
            sr = 24000 if "suspense" in profile.get("ref_audio", "") else 44100
            _write_test_sine_wav(save_path, sr=sr, duration=0.7)
            return True

        stitched = os.path.join(self.tmp, "stitched.wav")
        ok = stitch_emotional_segments(
            "[fear]यह पहला वाक्य है।[/fear] [pause:0.5s] [fast]दूसरा वाक्य।[/fast]",
            tts_backend_fn=_fake_backend,
            out_wav=stitched,
        )
        self.assertTrue(ok)
        with wave.open(stitched, "rb") as w:
            dur = w.getnframes() / w.getframerate()
        self.assertGreater(dur, 1.5)

    def test_speak_to_show_span_lock_in_subtitles(self):
        line = "साल 2026 में Supreme Court ने ₹500 Cr का जुर्माना लगाया।"
        spec = build_speak_show_alignment_spec(line)
        speak_timings = ForcedAligner.estimate_proportional_timings(spec["speak_words"], audio_duration=6.0)
        mapped = ForcedAligner.map_speak_timings_to_show_spans(
            speak_timings, spec["display_spans"], audio_duration=6.0
        )

        scene = SceneDefinition(
            scene_id="scene_01",
            chapter_index=1,
            title="SC Notice",
            narration=line,
            visual_description="Courtroom",
            footage_queries=["court"],
            ai_prompt="courtroom",
            duration=6.0,
            transition="fade",
            bgm_mood="intense",
            sfx_tag="paper_rustle",
            subtitle_text=line,
            word_timings=mapped,
        )
        chunks = SubtitleGenerator._scene_chunks(scene, words_per_chunk=4, max_chunk_graphemes=30)
        joined_lines = ["\n".join(ch["lines"]) for ch in chunks]
        full_rendered = "\n".join(joined_lines)
        # Atomic spans must never be torn across chunks/lines
        self.assertIn("₹500 Cr", full_rendered)
        self.assertIn("Supreme Court", full_rendered)
        self.assertIn("2026", full_rendered)

        manifest = StoryboardManifest(topic="Court", language="hi", target_duration=6, scenes=[scene])
        ass_path = os.path.join(self.tmp, "locked.ass")
        SubtitleGenerator.generate_ass(manifest, ass_path, style_mode="ass_karaoke")
        with open(ass_path, "r", encoding="utf-8-sig") as f:
            ass_txt = f.read()
        self.assertIn("₹500 Cr", ass_txt)
        self.assertIn("Supreme Court", ass_txt)

    def test_foley_sfx_and_archive_radio_mixer(self):
        self.assertIsNotNone(resolve_sfx_clip("news_card"))
        sfx_wav = os.path.join(self.tmp, "sfx_beats.wav")
        SoundEffectsEngine.generate_sfx(
            "news_card",
            duration=6.0,
            output_path=sfx_wav,
            visual_beats=[
                {"visual_type": "news_card", "duration": 3.0, "sfx_tag": "paper_rustle"},
                {"visual_type": "stat_card", "duration": 3.0, "sfx_tag": "subtle_pop"},
            ],
        )
        self.assertTrue(os.path.exists(sfx_wav))
        self.assertTrue(os.path.getsize(sfx_wav) > 100_000)

        voice_wav = os.path.join(self.tmp, "v.wav")
        bgm_wav = os.path.join(self.tmp, "b.wav")
        out_mix = os.path.join(self.tmp, "mix_archive.wav")
        _write_test_sine_wav(voice_wav, sr=44100, duration=4.0, freq=190.0)
        BackgroundMusicEngine.generate_thematic_bgm(bgm_wav, duration=4.0, mood="mysterious")
        ok = AudioProductionMixer.mix_scene_audio(
            voice_wav, sfx_wav, bgm_wav, out_mix, duration=4.0, archive_quote=True
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out_mix))


if __name__ == "__main__":
    unittest.main()
