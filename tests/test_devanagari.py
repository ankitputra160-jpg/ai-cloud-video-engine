"""
tests/test_devanagari.py - Tests for Hindi Devanagari Matra Integrity, Normalization, & Bundled Fonts
"""
import os
import unittest
from engine.text.devanagari import (
    contains_devanagari,
    get_fonts_dir,
    grapheme_len,
    normalize_devanagari,
    resolve_devanagari_font,
    split_graphemes,
    wrap_indic_text,
)


class TestDevanagariEngine(unittest.TestCase):
    def test_bundled_fonts_exist(self):
        fonts_dir = get_fonts_dir()
        self.assertTrue(os.path.isdir(fonts_dir))
        font_path = resolve_devanagari_font("NotoSansDevanagari-VF.ttf")
        self.assertIsNotNone(font_path)
        self.assertTrue(os.path.exists(font_path))

    def test_matra_normalization_and_grapheme_clusters(self):
        # "विज्ञान और प्रक्रिया" in decomposed form -> NFC must keep matras bound
        word = "विज्ञान"
        norm = normalize_devanagari(word)
        self.assertTrue(contains_devanagari(norm))
        clusters = split_graphemes(norm)
        # Should keep 'वि' (व + ि) and 'ज्ञा' (ज + ् + ञ + ा) intact as clusters
        self.assertIn("वि", clusters)
        self.assertLess(len(clusters), len(norm))

    def test_grapheme_safe_wrapping_never_splits_matra(self):
        sentence = "प्राचीन भारतीय खगोलशास्त्र और विज्ञान की अद्भुत कहानी।"
        lines = wrap_indic_text(sentence, max_graphemes=20)
        self.assertTrue(len(lines) >= 2)
        for line in lines:
            # No line may begin with a bare vowel sign (matra) or halant!
            first_char = line[0]
            self.assertFalse("\u093E" <= first_char <= "\u094D", f"Line started with orphaned matra: {line}")
            self.assertTrue(grapheme_len(line) <= 20)


if __name__ == "__main__":
    unittest.main()
