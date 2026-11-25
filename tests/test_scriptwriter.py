"""
tests/test_scriptwriter.py - Tests for Documentary Scriptwriting & Narrative Structure
"""
import unittest
from engine.research import ResearchDossier
from engine.scriptwriter import ScriptWriter, DocumentaryScript

class TestScriptWriter(unittest.TestCase):
    def setUp(self):
        self.dossier = ResearchDossier(
            topic="Space Exploration",
            title="Space Exploration",
            summary="Space exploration is the use of astronomy and space technology to explore outer space.",
            key_facts=["In 1957 Sputnik 1 was launched.", "In 1969 Neil Armstrong stepped on the Moon."],
            timeline=[{"year": "1969", "event": "Moon landing"}],
            entities=["NASA", "Sputnik"],
            sources=["https://en.wikipedia.org/wiki/Space_exploration"]
        )

    def test_english_script_generation(self):
        writer = ScriptWriter(language="en")
        script = writer.generate_script(self.dossier, target_duration=60)
        self.assertIsInstance(script, DocumentaryScript)
        self.assertEqual(script.language, "en")
        self.assertTrue(len(script.chapters) >= 3)
        self.assertTrue(len(script.hook) > 10)
        self.assertTrue(len(script.conclusion) > 10)
        self.assertTrue(script.total_words > 20)

    def test_hindi_script_generation(self):
        writer = ScriptWriter(language="hi")
        script = writer.generate_script(self.dossier, target_duration=60)
        self.assertEqual(script.language, "hi")
        self.assertTrue(len(script.chapters) >= 3)
        self.assertIn("इतिहास", script.chapters[0].narration)

    def test_short_duration_scaling(self):
        # 10s video must produce compact chapters
        writer = ScriptWriter(language="en")
        script_10s = writer.generate_script(self.dossier, target_duration=10)
        self.assertEqual(len(script_10s.chapters), 2)
        total_time = sum(ch.target_seconds for ch in script_10s.chapters)
        self.assertAlmostEqual(total_time, 10.0, delta=0.5)

if __name__ == "__main__":
    unittest.main()
