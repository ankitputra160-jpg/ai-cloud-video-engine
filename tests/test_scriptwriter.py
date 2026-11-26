"""
tests/test_scriptwriter.py - Tests for Documentary & 2D Scriptwriting (10s to 25-min Scaling)
"""
import unittest
from engine.research import ResearchDossier
from engine.scriptwriter import ScriptWriter, DocumentaryScript


class TestScriptWriter(unittest.TestCase):
    def setUp(self):
        self.dossier = ResearchDossier(
            topic="Space Exploration",
            title="Space Exploration",
            english_title="Space Exploration",
            summary="Space exploration is the use of astronomy and space technology to explore outer space.",
            key_facts=[
                "In 1957 Sputnik 1 became the first artificial Earth satellite.",
                "In 1969 Apollo 11 landed the first humans on the Moon.",
                "In 1977 Voyager 1 launched to study the outer Solar System.",
                "In 1990 the Hubble Space Telescope entered low Earth orbit.",
            ],
            timeline=[{"year": "1957", "event": "Sputnik 1"}, {"year": "1969", "event": "Moon landing"}],
            entities=["NASA", "Sputnik", "Apollo 11"],
            sources=["https://en.wikipedia.org/wiki/Space_exploration"]
        )

    def test_english_script_generation(self):
        writer = ScriptWriter(language="en", style="Documentary")
        script = writer.generate_script(self.dossier, target_duration=60)
        self.assertIsInstance(script, DocumentaryScript)
        self.assertEqual(script.language, "en")
        self.assertTrue(len(script.chapters) >= 4)
        self.assertTrue(len(script.hook) > 10)
        self.assertTrue(len(script.conclusion) > 10)
        self.assertTrue(script.total_words > 20)

    def test_hindi_script_generation_and_non_repetition(self):
        writer = ScriptWriter(language="hi", style="2D Animation")
        script = writer.generate_script(self.dossier, target_duration=75)
        self.assertEqual(script.language, "hi")
        self.assertEqual(script.style, "2D Animation")
        self.assertTrue(len(script.chapters) >= 4)
        self.assertIn("इतिहास", script.chapters[0].narration)
        # Middle scenes must NOT duplicate identical boilerplate
        narrations = [ch.narration for ch in script.chapters]
        self.assertEqual(len(narrations), len(set(narrations)))
        # 2D production markdown must be generated cleanly
        md = script.to_2d_markdown()
        self.assertIn("2D Production Script", md)
        self.assertIn("2D Visual Prompt", md)

    def test_long_form_25_minute_scaling(self):
        writer = ScriptWriter(language="en", style="2D Animation")
        script_25m = writer.generate_script(self.dossier, target_duration=1500)
        # 25 minutes (~1500s) scales up to ~115 visual scenes
        self.assertTrue(80 <= len(script_25m.chapters) <= 120)
        total_time = sum(ch.target_seconds for ch in script_25m.chapters)
        self.assertAlmostEqual(total_time, 1500.0, delta=1.0)

    def test_short_duration_scaling(self):
        writer = ScriptWriter(language="en")
        script_10s = writer.generate_script(self.dossier, target_duration=10)
        self.assertEqual(len(script_10s.chapters), 2)
        total_time = sum(ch.target_seconds for ch in script_10s.chapters)
        self.assertAlmostEqual(total_time, 10.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
