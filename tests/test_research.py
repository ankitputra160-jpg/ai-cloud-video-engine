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

    def test_rss_parsing_and_fact_sheet_locking(self):
        import os, tempfile, json
        from unittest.mock import patch, MagicMock
        rss_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<rss><channel><item>'
            b'<title>Supreme Court hears electoral petition - The Hindu</title>'
            b'<link>https://example.com/news1</link>'
            b'<pubDate>Wed, 15 Jan 2026 10:00:00 GMT</pubDate>'
            b'<source>The Hindu</source>'
            b'</item></channel></rss>'
        )
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            news = self.engine._fetch_rss_news("Supreme Court")
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["source"], "The Hindu")
        self.assertEqual(news[0]["headline"], "Supreme Court hears electoral petition")

        dossier = ResearchDossier(topic="CJP Protest", title="CJP Protest", summary="Summary", news_items=news)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fact_sheet.json")
            dossier.save_fact_sheet(p)
            with open(p, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["news_items"][0]["source"], "The Hindu")

    def test_unrelated_wikipedia_homonym_is_rejected(self):
        self.assertFalse(
            ResearchEngine._is_wiki_result_relevant(
                "2026 Supreme Court 500 Cr Investigation",
                "Luigi Mangione",
                "American suspect arrested in 2024 criminal case",
            )
        )
        self.assertTrue(
            ResearchEngine._is_wiki_result_relevant(
                "Supreme Court of India",
                "Supreme Court of India",
                "Highest judicial forum and final court of appeal in India",
            )
        )

if __name__ == "__main__":
    unittest.main()
