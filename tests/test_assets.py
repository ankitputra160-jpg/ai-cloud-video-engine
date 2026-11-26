"""
tests/test_assets.py - Tests for Multi-Tier Visual Asset Providers (Wikimedia, NASA, Pollinations, 2D Cards)
"""
import os
import tempfile
import unittest
from engine.assets.ai_visuals import CinematicMotionVisualProvider
from engine.assets.nasa import NasaMediaProvider
from engine.assets.pexels import PexelsProvider
from engine.assets.pollinations import PollinationsAIProvider
from engine.assets.wikimedia import WikimediaCommonsProvider
from engine.renderer.ffmpeg_utils import get_duration


class TestVisualAssets(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_pexels_api_validation_bug7(self):
        empty_prov = PexelsProvider(api_key="")
        self.assertFalse(empty_prov.is_available())
        short_prov = PexelsProvider(api_key="12345")
        self.assertFalse(short_prov.is_available())
        valid_prov = PexelsProvider(api_key="sample_valid_looking_key_12345678")
        self.assertTrue(valid_prov.is_available())

    def test_wikimedia_and_nasa_and_pollinations_providers(self):
        wiki_prov = WikimediaCommonsProvider()
        self.assertTrue(wiki_prov.is_available())
        self.assertEqual(wiki_prov.name, "wikimedia_commons")

        nasa_prov = NasaMediaProvider()
        self.assertTrue(nasa_prov.is_topic_relevant(["Ancient Indian Astronomy telescope"]))
        self.assertFalse(nasa_prov.is_topic_relevant(["Victorian carpentry tools"]))

        ai_prov = PollinationsAIProvider()
        self.assertTrue(ai_prov.is_available())
        self.assertEqual(ai_prov.name, "pollinations_ai_2d")

    def test_cinematic_motion_generator_bug4(self):
        motion_gen = CinematicMotionVisualProvider(width=1280, height=720, fps=25)
        out_clip = os.path.join(self.temp_dir, "test_motion.mp4")

        result = motion_gen.generate_motion_clip(
            out_clip, title="प्राचीन भारतीय खगोलशास्त्र", duration=3.0, mood="epic", date_badge="499 CE"
        )
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(out_clip))
        self.assertTrue(os.path.getsize(out_clip) > 5000)

        dur = get_duration(out_clip)
        self.assertAlmostEqual(dur, 3.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
