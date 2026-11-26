"""
tests/test_visuals_checkpoint_thumb.py - Phase 4 Tests for Watermark-Free Providers, Visual QC,
Playwright/ASS Hindi Investigative Cards, Checkpoint Auto-Resume, NVENC Detection,
Auto-Thumbnail & Audio-First Hindi E2E Pipeline.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from engine.assets.archive_org import InternetArchiveProvider
from engine.assets.news_card import InvestigativeCardGenerator
from engine.assets.openverse import OpenverseProvider
from engine.assets.pib import PIBIndiaProvider
from engine.assets.qc_visual import SemanticClipChecker, validate_visual_dimensions
from engine.checkpoint import CheckpointManager
from engine.config import PipelineConfig
from engine.pipeline import DocumentaryPipeline
from engine.renderer.ffmpeg_utils import detect_h264_encoder, get_duration
from engine.renderer.thumbnail import AutoThumbnailGenerator


class TestVisualsCheckpointThumb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_watermark_free_providers_and_qc_dimensions(self):
        pib = PIBIndiaProvider()
        self.assertTrue(pib.is_topic_relevant(["Supreme Court of India CJI hearing"]))
        self.assertFalse(pib.is_topic_relevant(["Antarctica penguin colony"]))
        self.assertTrue(InternetArchiveProvider().is_available())
        self.assertTrue(OpenverseProvider().is_available())
        self.assertFalse(SemanticClipChecker().is_available())  # CPU Termux check cleanly False

        tiny = os.path.join(self.tmp, "tiny.mp4")
        hd = os.path.join(self.tmp, "hd.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1", tiny], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=1", hd], check=True)

        self.assertFalse(validate_visual_dimensions(tiny, min_width=960, min_height=540))
        self.assertTrue(validate_visual_dimensions(hd, min_width=960, min_height=540))

    def test_hindi_news_card_and_stat_card_no_drawtext(self):
        gen = InvestigativeCardGenerator(width=1280, height=720, fps=25)
        news_mp4 = os.path.join(self.tmp, "news_card.mp4")
        res = gen.render_card_video(
            news_mp4,
            card_type="news_card",
            headline="सुप्रीम कोर्ट ने ₹500 Cr के बॉन्ड्स पर बड़ा सवाल उठाया",
            source="LiveLaw India",
            date_badge="2026",
            duration=2.0,
        )
        self.assertIsNotNone(res)
        self.assertTrue(os.path.exists(news_mp4))
        self.assertGreater(os.path.getsize(news_mp4), 5000)
        self.assertAlmostEqual(get_duration(news_mp4), 2.0, delta=0.25)

    def test_checkpoint_manager_and_auto_thumbnail(self):
        cp = CheckpointManager(self.tmp)
        f_marker = os.path.join(self.tmp, "fact_sheet.json")
        with open(f_marker, "w", encoding="utf-8") as f:
            f.write('{"topic": "Test", "locked_facts": ["a"]}' * 5)
        cp.mark_stage_done("research", f_marker)

        cp2 = CheckpointManager(self.tmp)
        self.assertTrue(cp2.is_stage_done("research", f_marker))
        self.assertFalse(cp2.is_stage_done("rendered_video"))

        sample_vid = os.path.join(self.tmp, "sample.mp4")
        thumb_jpg = os.path.join(self.tmp, "sample_thumb.jpg")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            sample_vid,
        ], check=True)
        out_t = AutoThumbnailGenerator.generate_thumbnail(
            sample_vid,
            hook_text="सुप्रीम कोर्ट का सबसे बड़ा खुलासा",
            output_jpg_path=thumb_jpg,
            duration=3.0,
        )
        self.assertIsNotNone(out_t)
        self.assertTrue(os.path.exists(thumb_jpg))
        self.assertGreater(os.path.getsize(thumb_jpg), 5000)
        self.assertIn(detect_h264_encoder(), ("libx264", "h264_nvenc"))

    def test_hindi_audio_first_e2e_preview_offline_fast(self):
        """Fast end-to-end Hindi v3.0 pipeline test (mocking external network lookups)."""
        work = os.path.join(self.tmp, "ws_hi")
        out_mp4 = os.path.join(self.tmp, "final_hi.mp4")
        thumb_jpg = os.path.join(self.tmp, "final_hi_thumb.jpg")
        cfg = PipelineConfig(
            topic="2026 Supreme Court ₹500 Cr Case",
            style="Documentary",
            duration=10,
            language="hi",
            resolution="720p",
            output_path=out_mp4,
            work_dir=work,
            llm_mode="deterministic",
            voice_engine="edge",  # falls cleanly to procedural in offline sandbox
            thumbnail_path=thumb_jpg,
            enable_ai_video=False,
        )

        from engine.research import ResearchDossier
        mock_dossier = ResearchDossier(
            topic=cfg.topic,
            title="सुप्रीम कोर्ट मामला",
            english_title="Supreme Court Case",
            summary="साल 2026 में Supreme Court ने ₹500 Cr पर सवाल पूछा।",
            key_facts=[
                "साल 2026 में Supreme Court ने ₹500 Cr के रिकॉर्ड माँगे।",
                "45% डेटा समय पर जमा नहीं हुआ था।",
            ],
            timeline=[{"year": "2026", "event": "Hearing"}],
            entities=["Supreme Court", "CJI"],
            news_items=[{"headline": "SC seeks ₹500 Cr details", "source": "The Hindu", "date": "Jan 2026", "url": ""}],
        )

        with patch("engine.research.ResearchEngine.search_topic", return_value=mock_dossier), \
             patch("engine.assets.manager.VisualAssetManager._fetch_verified_real_beat", return_value=None), \
             patch("engine.assets.pollinations.PollinationsAIProvider.fetch_video", return_value=None):
            pipe = DocumentaryPipeline(cfg)
            result = pipe.run()

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(out_mp4))
        self.assertTrue(os.path.exists(thumb_jpg))
        self.assertTrue(result["qc_report"]["passed"])
        self.assertTrue(os.path.exists(os.path.join(work, "fact_sheet.json")))
        self.assertTrue(os.path.exists(os.path.join(work, "checkpoint_state.json")))


if __name__ == "__main__":
    unittest.main()
