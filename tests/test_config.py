"""
tests/test_config.py - Tests for configuration, sanitization, and profile management
"""
import unittest
from engine.config import PipelineConfig, PROFILES, VOICE_CONFIGS

class TestPipelineConfig(unittest.TestCase):
    def test_topic_sanitization(self):
        # Shell metacharacters and control characters must be stripped
        dirty = "Ancient Space; rm -rf / && `whoami`\n\t"
        clean = PipelineConfig.sanitize_topic(dirty)
        self.assertNotIn(";", clean)
        self.assertNotIn("`", clean)
        self.assertNotIn("\n", clean)
        self.assertIn("Ancient Space", clean)

    def test_duration_clamping(self):
        # Below min duration
        cfg_low = PipelineConfig(topic="Test", duration=3)
        self.assertEqual(cfg_low.duration, 10)

        # Above max duration
        cfg_high = PipelineConfig(topic="Test", duration=9999)
        self.assertEqual(cfg_high.duration, 600)

        # Normal duration
        cfg_normal = PipelineConfig(topic="Test", duration=45)
        self.assertEqual(cfg_normal.duration, 45)

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
