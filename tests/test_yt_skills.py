import json
import os
import tempfile
import unittest

from engine.storyboard import SceneDefinition, StoryboardManifest
from engine.yt_skills import (
    export_youtube_package_and_chapters,
    lint_title_thumbnail_pair,
    load_hook_formulas,
    score_bilingual_hook,
)


class TestYouTubeSkills(unittest.TestCase):
    def test_hook_formulas_and_bilingual_scoring(self):
        formulas = load_hook_formulas()
        self.assertGreaterEqual(len(formulas), 8)

        strong = score_bilingual_hook(
            "रात के 12 बजे आपके फ़ोन पर CBI का वीडियो कॉल आता है—और ₹1,935 Crore ठगी का यही जाल आपकी जमा-पूँजी छीन सकता है। क्या आप बच पाएंगे?"
        )
        self.assertEqual(strong["band"], "STRONG")
        self.assertGreaterEqual(strong["verdict"], 72)

    def test_title_thumbnail_lint_catches_overlap(self):
        overlap = lint_title_thumbnail_pair("Digital Arrest Scam Secrets", "Digital Arrest Secrets")
        self.assertTrue(any("duplicate" in i[0] for i in overlap["issues"]))

        clean = lint_title_thumbnail_pair(
            "Digital Arrest & AI Voice Cloning Scam Exposed",
            "सावधान! ₹1,935 Crore ठगी",
        )
        self.assertFalse(any("duplicate" in i[0] for i in clean["issues"]))

    def test_export_youtube_package_and_chapters(self):
        scenes = [
            SceneDefinition(
                scene_id=f"scene_{i+1:02d}",
                chapter_index=i + 1,
                title=f"अध्याय {i+1}",
                narration="रात के 12 बजे आपके फ़ोन पर CBI का वीडियो कॉल आता है—₹1,935 Crore ठगी का सच क्या है?",
                visual_description="doc",
                footage_queries=["cyber"],
                ai_prompt="cyber",
                duration=12.0,
                transition="fade",
                bgm_mood="mysterious",
                sfx_tag="soft_whoosh",
                subtitle_text="रात के 12 बजे आपके फ़ोन पर कॉल।",
            )
            for i in range(4)
        ]
        manifest = StoryboardManifest(
            topic="Digital Arrest Exposed",
            language="hi",
            target_duration=48,
            thumbnail_hook="सावधान! ₹1,935 Crore ठगी",
            scenes=scenes,
        )
        with tempfile.TemporaryDirectory() as td:
            srt = os.path.join(td, "sub.srt")
            with open(srt, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:03,000\nHello\n\n2\n00:00:03,200 --> 00:00:06,000\nWorld\n")
            res = export_youtube_package_and_chapters(manifest, srt, td)
            self.assertTrue(os.path.exists(res["chapters_txt"]))
            self.assertTrue(os.path.exists(res["package_json"]))
            with open(res["chapters_txt"], "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.read().splitlines() if l.strip()]
            self.assertTrue(lines[0].startswith("0:00 "))
            with open(res["package_json"], "r", encoding="utf-8") as f:
                pkg = json.load(f)
            self.assertTrue(pkg["chapters_valid"])


if __name__ == "__main__":
    unittest.main()
