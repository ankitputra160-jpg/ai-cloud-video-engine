"""
tests/test_qc.py - Tests for Automated Quality Control & Integrity Inspection (Bug 12 Fix)
"""
import unittest
import os
import tempfile
import subprocess
from engine.config import PipelineConfig
from engine.qc.inspector import QualityInspector, QCReport

class TestQualityControl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = PipelineConfig(topic="QC Test", resolution="720p")
        self.inspector = QualityInspector(self.config)

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    def test_missing_file_qc(self):
        report = self.inspector.inspect_video("/non/existent/video.mp4", expected_duration=10.0)
        self.assertFalse(report.passed)
        self.assertEqual(report.status, "FAILED")
        self.assertTrue(len(report.issues) > 0)

    def test_valid_video_qc_bug12(self):
        """Verifies Bug 12 fix: comprehensive validation of container, streams, duration, and FPS."""
        valid_mp4 = os.path.join(self.temp_dir, "valid.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=3",
            "-f", "lavfi", "-i", "sine=f=440:d=3",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            valid_mp4
        ], capture_output=True)

        report = self.inspector.inspect_video(valid_mp4, expected_duration=3.0)
        self.assertTrue(report.passed)
        self.assertTrue(report.has_video_stream)
        self.assertTrue(report.has_audio_stream)
        self.assertEqual(report.width, 1280)
        self.assertEqual(report.height, 720)
        self.assertAlmostEqual(report.actual_duration, 3.0, delta=0.5)
        self.assertIsNotNone(report.integrated_lufs)

    def test_ebur128_and_subtitle_sync_qc(self):
        """Verifies EBU R128 loudness measurement and audio-subtitle sync verification."""
        valid_mp4 = os.path.join(self.temp_dir, "loud_sync.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=3",
            "-f", "lavfi", "-i", "sine=f=440:d=3",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=6",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            valid_mp4
        ], capture_output=True)

        good_srt = os.path.join(self.temp_dir, "good.srt")
        with open(good_srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,100 --> 00:00:02,800\n₹7 Crore CBI\n")

        rep_good = self.inspector.inspect_video(valid_mp4, expected_duration=3.0, subtitle_path=good_srt)
        self.assertTrue(rep_good.passed)
        self.assertTrue(rep_good.subtitle_sync_ok)
        self.assertEqual(rep_good.subtitle_cue_count, 1)
        self.assertIsNotNone(rep_good.integrated_lufs)

        bad_srt = os.path.join(self.temp_dir, "bad.srt")
        with open(bad_srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,100 --> 00:00:09,500\nOverflow cue\n")

        rep_bad = self.inspector.inspect_video(valid_mp4, expected_duration=3.0, subtitle_path=bad_srt)
        self.assertFalse(rep_bad.subtitle_sync_ok)
        self.assertTrue(any("overflow" in w.lower() for w in rep_bad.warnings))

if __name__ == "__main__":
    unittest.main()
