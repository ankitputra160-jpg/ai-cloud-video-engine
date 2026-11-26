"""
tests/test_config.py - Tests for configuration, sanitization, 25-min limits, and 2D style modes
"""
import unittest
from engine.config import PipelineConfig, MAX_DURATION_SECONDS

class TestPipelineConfig(unittest.TestCase):
    def test_topic_sanitization(self):
        dirty = "Ancient Space; rm -rf / && `whoami`\n\t"
        clean = PipelineConfig.sanitize_topic(dirty)
        self.assertNotIn(";", clean)
        self.assertNotIn("`", clean)
        self.assertNotIn("\n", clean)
        self.assertIn("Ancient Space", clean)

    def test_duration_clamping_25min(self):
        cfg_low = PipelineConfig(topic="Test", duration=3)
        self.assertEqual(cfg_low.duration, 10)

        # Max duration upgraded to 25 minutes (1500 seconds)
        cfg_25min = PipelineConfig(topic="Test", duration=1500)
        self.assertEqual(cfg_25min.duration, 1500)

        cfg_high = PipelineConfig(topic="Test", duration=9999)
        self.assertEqual(cfg_high.duration, MAX_DURATION_SECONDS)
        self.assertEqual(cfg_high.duration, 1500)

    def test_2d_animation_and_subtitle_modes(self):
        cfg_2d = PipelineConfig(topic="Test", style="2D Animation", subtitle_style="ass_karaoke")
        self.assertTrue(cfg_2d.is_2d_style)
        self.assertEqual(cfg_2d.subtitle_style, "ass_karaoke")

        cfg_doc = PipelineConfig(topic="Test", style="Documentary", subtitle_style="pill_box", voice_engine="piper")
        self.assertFalse(cfg_doc.is_2d_style)
        self.assertEqual(cfg_doc.subtitle_style, "pill_box")
        self.assertEqual(cfg_doc.voice_engine, "piper")
        self.assertIn("piper_onnx_url", cfg_doc.voice_settings)

    def test_language_and_voice(self):
        cfg_en = PipelineConfig(topic="Test", language="en")
        self.assertEqual(cfg_en.language, "en")
        self.assertIn("primary", cfg_en.voice_settings)

        cfg_hi = PipelineConfig(topic="Test", language="hi")
        self.assertEqual(cfg_hi.language, "hi")
        self.assertIn("primary", cfg_hi.voice_settings)

    def test_resolution_profile(self):
        cfg_1080p = PipelineConfig(topic="Test", resolution="1080p")
        self.assertEqual(cfg_1080p.profile.width, 1920)
        self.assertEqual(cfg_1080p.profile.height, 1080)

        cfg_4k = PipelineConfig(topic="Test", resolution="4k")
        self.assertEqual(cfg_4k.profile.width, 3840)
        self.assertEqual(cfg_4k.profile.height, 2160)

if __name__ == "__main__":
    unittest.main()
