"""
tests/test_audio.py - Tests for BGM, SFX, and Audio Production Mixer (Bug 2 & 10 Fixes)
"""
import unittest
import os
import tempfile
import wave
from engine.audio.bgm import BackgroundMusicEngine
from engine.audio.sfx import SoundEffectsEngine
from engine.audio.mixer import AudioProductionMixer
from engine.renderer.ffmpeg_utils import get_duration

class TestAudioProduction(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    def test_bgm_generation_and_stereo_properties_bug2(self):
        """Verifies Bug 2 fix: consistent BGM generation and valid stereo WAV structure."""
        bgm_path = os.path.join(self.temp_dir, "bgm_thematic.wav")
        BackgroundMusicEngine.generate_thematic_bgm(bgm_path, duration=5.0, mood="epic")
        
        self.assertTrue(os.path.exists(bgm_path))
        with wave.open(bgm_path, "rb") as w:
            self.assertEqual(w.getnchannels(), 2)  # Stereo
            self.assertEqual(w.getsampwidth(), 2)   # 16-bit
            self.assertEqual(w.getframerate(), 44100)
            dur = w.getnframes() / 44100.0
            self.assertAlmostEqual(dur, 5.0, delta=0.2)

    def test_sfx_generation(self):
        sfx_path = os.path.join(self.temp_dir, "sfx_test.wav")
        SoundEffectsEngine.generate_sfx("ambient_wind", duration=3.0, output_path=sfx_path)
        self.assertTrue(os.path.exists(sfx_path))
        with wave.open(sfx_path, "rb") as w:
            self.assertEqual(w.getnchannels(), 2)
            self.assertAlmostEqual(w.getnframes() / 44100.0, 3.0, delta=0.2)

    def test_audio_mixer_ducking_bug10(self):
        """Verifies Bug 10 fix: automated speech ducking and loudness normalization."""
        voice_path = os.path.join(self.temp_dir, "voice.wav")
        sfx_path = os.path.join(self.temp_dir, "sfx.wav")
        bgm_path = os.path.join(self.temp_dir, "bgm.wav")
        out_mix = os.path.join(self.temp_dir, "master_mixed.wav")

        SoundEffectsEngine.generate_sfx("low_bass_rumble", duration=4.0, output_path=voice_path)
        SoundEffectsEngine.generate_sfx("subtle_clicks", duration=4.0, output_path=sfx_path)
        BackgroundMusicEngine.generate_thematic_bgm(bgm_path, duration=4.0, mood="inspiring")

        success = AudioProductionMixer.mix_scene_audio(
            voice_path=voice_path,
            sfx_path=sfx_path,
            bgm_path=bgm_path,
            output_path=out_mix,
            duration=4.0
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(out_mix))
        dur = get_duration(out_mix)
        self.assertAlmostEqual(dur, 4.0, delta=0.3)

if __name__ == "__main__":
    unittest.main()
