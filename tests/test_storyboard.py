"""
tests/test_storyboard.py - Tests for Dynamic Storyboard Generation & Schema Integrity (Bug 1 Fix)
"""
import unittest
import tempfile
import os
from engine.research import ResearchDossier
from engine.scriptwriter import ScriptWriter
from engine.storyboard import StoryboardEngine, StoryboardManifest, SceneDefinition

class TestStoryboardEngine(unittest.TestCase):
    def setUp(self):
        dossier = ResearchDossier(
            topic="Ocean Wonders",
            title="Ocean Wonders",
            summary="The deep ocean remains one of the final frontiers on planet Earth.",
            key_facts=["More than eighty percent of the ocean is unmapped."],
            sources=["https://en.wikipedia.org/wiki/Ocean"]
        )
        writer = ScriptWriter(language="en")
        self.script = writer.generate_script(dossier, target_duration=30)
        self.engine = StoryboardEngine()

    def test_storyboard_generation(self):
        manifest = self.engine.generate_storyboard(self.script)
        self.assertIsInstance(manifest, StoryboardManifest)
        self.assertEqual(len(manifest.scenes), len(self.script.chapters))
        self.assertAlmostEqual(manifest.total_duration, 30.0, delta=1.0)

        for scene in manifest.scenes:
            self.assertIsInstance(scene, SceneDefinition)
            self.assertTrue(scene.scene_id.startswith("scene_"))
            self.assertTrue(len(scene.footage_queries) > 0)
            self.assertTrue(len(scene.ai_prompt) > 20)
            self.assertIn(scene.transition, StoryboardEngine.TRANSITIONS)

    def test_manifest_json_serialization_fix_bug1(self):
        """Verify that manifest JSON serialization and deserialization does NOT suffer from Bug 1 dictionary mismatch."""
        manifest = self.engine.generate_storyboard(self.script)
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            manifest.save_json(tmp_path)
            loaded_manifest = StoryboardManifest.load_json(tmp_path)
            self.assertEqual(len(loaded_manifest.scenes), len(manifest.scenes))
            self.assertEqual(loaded_manifest.scenes[0].scene_id, "scene_01")
            self.assertEqual(loaded_manifest.scenes[0].narration, manifest.scenes[0].narration)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
