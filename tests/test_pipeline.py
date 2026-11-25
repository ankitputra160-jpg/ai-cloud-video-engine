"""
tests/test_pipeline.py - End-to-End Integration Test for Documentary Production Pipeline
"""
import unittest
import os
import shutil
from engine.config import PipelineConfig
from engine.pipeline import DocumentaryPipeline

class TestDocumentaryPipelineE2E(unittest.TestCase):
    def setUp(self):
        self.work_dir = ".test_pipeline_workspace"
        self.output_mp4 = os.path.join(self.work_dir, "test_doc_output.mp4")
        if os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir)

    def tearDown(self):
        if os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir)

    def test_end_to_end_pipeline_execution(self):
        """Execute full documentary pipeline: Research -> Script -> Storyboard -> Assets -> Voice -> Audio -> Render -> QC."""
        config = PipelineConfig(
            topic="The History of Timekeeping",
            style="Historical",
            duration=10,  # 10 second fast integration test
            language="en",
            resolution="720p",
            output_path=self.output_mp4,
            work_dir=self.work_dir,
            enable_qc=True,
            burn_subtitles=True
        )

        pipeline = DocumentaryPipeline(config)
        result = pipeline.run()

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(self.output_mp4))
        self.assertTrue(os.path.getsize(self.output_mp4) > 10000)

        qc = result["qc_report"]
        self.assertTrue(qc["passed"])
        self.assertTrue(qc["has_video_stream"])
        self.assertTrue(qc["has_audio_stream"])
        self.assertEqual(qc["width"], 1280)
        self.assertEqual(qc["height"], 720)
        self.assertAlmostEqual(qc["actual_duration"], 10.0, delta=1.5)

if __name__ == "__main__":
    unittest.main()
