"""
tests/test_humanizer_pronunciation.py - Phase 2 Tests for HindiHumanizerCritic,
Dual-Layer Speak-vs-Show Span-ID Normalizer, LLM JSON Parsing & 3-Pass Batch Scriptwriting.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from engine.llm_client import UnifiedLLMClient
from engine.research import ResearchDossier
from engine.scriptwriter import ScriptWriter
from engine.storyboard import StoryboardEngine
from engine.text.humanizer import audit_hindi_beat, humanize_hindi_rule_based, strip_inline_tags
from engine.text.pronunciation import (
    build_speak_show_alignment_spec,
    integer_to_hindi_words,
    to_tts_tagged_text,
)


class TestHumanizerAndPronunciation(unittest.TestCase):
    def test_bookish_ai_hindi_is_purged(self):
        stiff = "निष्कर्षतः यह महज़ एक घटना नहीं, बल्कि अनियमितताओं का पुनरीक्षण है। आने वाला वक्त ही बताएगा।"
        audit = audit_hindi_beat(stiff)
        self.assertTrue(audit["needs_rewrite"])
        self.assertIn("महज़", audit["bookish_words"])
        self.assertIn("निष्कर्षतः", audit["bookish_words"])

        cleaned = humanize_hindi_rule_based(stiff)
        self.assertNotIn("महज़", cleaned)
        self.assertNotIn("निष्कर्षतः", cleaned)
        self.assertNotIn("पुनरीक्षण", cleaned)
        self.assertNotIn("आने वाला वक्त ही बताएगा", cleaned)

    def test_indian_numbers_and_years_to_hindi_words(self):
        self.assertEqual(integer_to_hindi_words(500), "पाँच सौ")
        self.assertEqual(integer_to_hindi_words(2026, as_year=True), "दो हज़ार छब्बीस")
        self.assertEqual(integer_to_hindi_words(1947, as_year=True), "उन्नीस सौ सैंतालीस")
        self.assertEqual(integer_to_hindi_words(45), "पैंतालीस")

    def test_dual_layer_speak_vs_show_span_mapping(self):
        line = "[slow]2026 में Supreme Court ने ₹500 Cr और 45% डेटा माँगा।[/slow] [pause:0.5s] CJI ने आदेश दिया।"
        tts_txt = to_tts_tagged_text(line)
        self.assertIn("[slow]", tts_txt)
        self.assertIn("[pause:0.5s]", tts_txt)
        self.assertIn("दो हज़ार छब्बीस", tts_txt)
        self.assertIn("सुप्रीम कोर्ट", tts_txt)
        self.assertIn("पाँच सौ करोड़ रुपये", tts_txt)
        self.assertIn("पैंतालीस परसेंट", tts_txt)
        self.assertIn("सी जे आई", tts_txt)

        spec = build_speak_show_alignment_spec(line)
        speak_words = spec["speak_words"]
        spans = spec["display_spans"]

        # Verify every span index maps accurately to exact slice in speak_words
        shows = [s["show"] for s in spans]
        self.assertIn("₹500 Cr", shows)
        self.assertIn("Supreme Court", shows)
        self.assertIn("45%", shows)
        self.assertIn("CJI", shows)

        cr_span = next(s for s in spans if s["show"] == "₹500 Cr")
        mapped = speak_words[cr_span["speak_start_idx"]:cr_span["speak_end_idx"] + 1]
        self.assertEqual(mapped, ["पाँच", "सौ", "करोड़", "रुपये"])

    def test_strip_inline_tags(self):
        tagged = "[fear]असली खेल यहीं शुरू होता है।[/fear] [pause:0.4s] [fast]देखो क्या हुआ![/fast]"
        self.assertEqual(strip_inline_tags(tagged), "असली खेल यहीं शुरू होता है। देखो क्या हुआ!")

    def test_llm_json_extraction_and_batched_25min_script(self):
        fenced = 'Here is output:\n```json\n{"beats": [{"title": "T1", "tagged_narration": "[slow]कहानी शुरू।[/slow]", "visual_prompt_en": "courtroom photo", "scene_type": "real_photo", "mood": "curious", "on_screen_date": "2026"}]}\n```'
        parsed = UnifiedLLMClient.extract_json_payload(fenced)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(len(parsed["beats"]), 1)

        dossier = ResearchDossier(
            topic="Test Topic",
            title="Test Topic",
            english_title="Test Topic",
            summary="Summary text.",
            key_facts=["Fact 1 from 2024.", "Fact 2 with ₹500 Cr budget."],
        )
        with tempfile.TemporaryDirectory() as d:
            fs_path = os.path.join(d, "fact_sheet.json")
            dossier.save_fact_sheet(fs_path)
            self.assertTrue(os.path.exists(fs_path))
            with open(fs_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["topic"], "Test Topic")

        # Mocked LLM must run batched generation cleanly even for 25-min (>30 scenes!)
        mock_client = UnifiedLLMClient(llm_mode="groq", groq_api_key="dummy_key_for_test")
        with patch.object(mock_client, "is_llm_available", return_value=True), \
             patch.object(mock_client, "generate_json", return_value={
                 "beats": [
                     {
                         "title": f"Beat {k}",
                         "tagged_narration": f"ज़रा सोचिए — साल 2026 में ₹500 Cr का सवाल उठा था। [pause:0.3s] {k}",
                         "visual_prompt_en": f"Supreme Court newsroom photo {k}",
                         "scene_type": "news_card",
                         "mood": "intense",
                         "on_screen_date": "2026",
                     }
                     for k in range(12)
                 ]
             }):
            writer = ScriptWriter(language="hi", llm_client=mock_client)
            script = writer.generate_script(dossier, target_duration=1200)
            self.assertTrue(len(script.chapters) > 30)
            sb = StoryboardEngine().generate_storyboard(script)
            self.assertTrue(len(sb.scenes[0].visual_beats) >= 2)


if __name__ == "__main__":
    unittest.main()
