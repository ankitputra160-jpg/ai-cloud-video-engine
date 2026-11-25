"""
tests/test_renderer.py - Tests for FFmpeg Execution & Video Assembly (Bug 9 Fix)
"""
import unittest
import os
import tempfile
import subprocess
from engine.config import PipelineConfig
from engine.renderer.ffmpeg_utils import safe_run_ffmpeg, get_media_info, get_duration
from engine.renderer.editor import VideoEditor

class TestRenderer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = PipelineConfig(topic="Test Render", work_dir=self.temp_dir, resolution="720p")
        self.editor = VideoEditor(self.config)

    def tearDown(self):
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except Exception:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except Exception:
                    pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_safe_run_ffmpeg_bug9(self):
        """Verifies Bug 9 fix: FFmpeg returns True on success, False on error, never crashing or ignoring code."""
        # Valid command
        valid_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-t", "1",
            os.path.join(self.temp_dir, "test_valid.mp4")
        ]
        self.assertTrue(safe_run_ffmpeg(valid_cmd, "Valid Test"))

        # Invalid command (bogus filter)
        invalid_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "non_existent_filter_xyz_123=invalid",
            os.path.join(self.temp_dir, "test_invalid.mp4")
        ]
        self.assertFalse(safe_run_ffmpeg(invalid_cmd, "Invalid Test"))

    def test_media_probing(self):
        sample_mp4 = os.path.join(self.temp_dir, "probe_sample.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=25:d=2",
            "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-c:v", "libx264", "-c:a", "aac",
            sample_mp4
        ], capture_output=True)

        info = get_media_info(sample_mp4)
        self.assertIn("streams", info)
        self.assertEqual(len(info["streams"]), 2)
        dur = get_duration(sample_mp4)
        self.assertAlmostEqual(dur, 2.0, delta=0.2)

if __name__ == "__main__":
    unittest.main()
