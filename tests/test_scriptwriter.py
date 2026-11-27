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
        writer = ScriptWriter(language="hi", style="2D Animation", llm_mode="deterministic")
        script = writer.generate_script(self.dossier, target_duration=75)
        self.assertEqual(script.language, "hi")
        self.assertEqual(script.style, "2D Animation")
        self.assertTrue(len(script.chapters) >= 4)
        # Must NOT contain bookish textbook AI clichés
        for ch in script.chapters:
            self.assertNotIn("निष्कर्षतः", ch.narration)
            self.assertNotIn("महज़", ch.narration)
            self.assertNotIn("अमिट विरासत", ch.narration)
            self.assertTrue(len(ch.speak_words) > 0)
            self.assertTrue(len(ch.display_spans) > 0)
        # Middle scenes must NOT duplicate identical boilerplate
        narrations = [ch.narration for ch in script.chapters]
        self.assertEqual(len(narrations), len(set(narrations)))
        # 2D production markdown must be generated cleanly
        md = script.to_2d_markdown()
        self.assertIn("2D Production Script", md)
        self.assertIn("Visual Prompt", md)

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

    def test_archive_quote_trigger_and_partial_llm_batch_recovery(self):
        from unittest.mock import MagicMock
        from engine.research import ResearchDossier

        dossier_q = ResearchDossier(
            topic="Court Case",
            title="सुप्रीम कोर्ट मामला",
            english_title="Supreme Court Case",
            summary="सुनवाई में ऐतिहासिक टिप्पणी हुई।",
            key_facts=["फैक्ट एक।", "फैक्ट दो।", "फैक्ट तीन।", "फैक्ट चार।", "फैक्ट पांच।", "फैक्ट छह।"],
            verified_quotes=[{"speaker": "Justice", "quote": "यह संवैधानिक मुद्दा है।"}],
            news_items=[{"headline": "SC Order", "source": "LiveLaw", "date": "2026"}],
        )
        writer_det = ScriptWriter(language="hi", llm_mode="deterministic")
        s_det = writer_det.generate_script(dossier_q, target_duration=75)
        self.assertTrue(any(ch.visual_type == "quote_card" and ch.is_archive_quote for ch in s_det.chapters))

        # Mock LLM: batch 1 returns valid JSON, batch 2 fails -> must keep batch 1 LLM beats!
        fake_llm = MagicMock()
        fake_llm.is_llm_available.return_value = True
        fake_llm.generate_json.side_effect = [
            {"beats": [{"title": f"LLM Beat {i}", "tagged_narration": f"असल कहानी बीट {i}।", "visual_prompt_en": f"Courtroom {i}"} for i in range(12)]},
            None,
            None,
        ]
        writer_llm = ScriptWriter(language="hi", llm_client=fake_llm)
        s_long = writer_llm.generate_script(dossier_q, target_duration=240)
        self.assertGreaterEqual(len(s_long.chapters), 14)
        self.assertEqual(s_long.chapters[0].title, "LLM Beat 0")


if __name__ == "__main__":
    unittest.main()
