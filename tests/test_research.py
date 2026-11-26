"""
tests/test_research.py - Tests for Autonomous Topic Research Engine
"""
import unittest
from engine.research import ResearchEngine, ResearchDossier

class TestResearchEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ResearchEngine(timeout=5)

    def test_fact_extraction(self):
        sample_text = (
            "The Great Pyramid of Giza was built around 2560 BC by Pharaoh Khufu. "
            "It is the oldest of the Seven Wonders of the Ancient World. "
            "It was designed using advanced astronomical alignments."
        )
        facts = self.engine._extract_facts(sample_text, "Pyramids")
        self.assertTrue(len(facts) >= 1)
        self.assertTrue(any("2560" in f or "Pharaoh" in f for f in facts))

    def test_timeline_extraction(self):
        sample_text = "In 1969 humans landed on the Moon. Later in 1972 the Apollo program concluded."
        timeline = self.engine._extract_timeline(sample_text)
        self.assertTrue(len(timeline) >= 1)
        years = [item["year"] for item in timeline]
        self.assertIn("1969", years)

    def test_research_dossier_structure(self):
        # Offline guaranteed fallback test
        dossier = self.engine.search_topic("Origins of Aviation")
        self.assertIsInstance(dossier, ResearchDossier)
        self.assertTrue(len(dossier.title) > 0)
        self.assertTrue(len(dossier.summary) > 0)
        self.assertTrue(len(dossier.key_facts) > 0)
        
        # Test serialization
        d_dict = dossier.to_dict()
        self.assertEqual(d_dict["topic"], "Origins of Aviation")
        self.assertIn("sources", d_dict)
        self.assertIn("english_title", d_dict)

    def test_hindi_sentence_extraction(self):
        hindi_text = (
            "प्राचीन भारत में आर्यभट्ट ने वर्ष 499 में खगोल विज्ञान का अद्भुत ग्रंथ लिखा। "
            "सूर्य सिद्धांत की गणना आज भी सटीक मानी जाती है।"
        )
        facts = self.engine._extract_facts(hindi_text, "Astronomy")
        self.assertTrue(len(facts) >= 2)
        self.assertTrue(any("आर्यभट्ट" in f for f in facts))

if __name__ == "__main__":
    unittest.main()
