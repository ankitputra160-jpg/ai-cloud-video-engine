"""
engine/text - Unicode text normalization, Indic/Devanagari matra shaping, and grapheme clustering.
"""
from engine.text.devanagari import (
    normalize_devanagari,
    contains_devanagari,
    split_graphemes,
    grapheme_len,
    wrap_indic_text,
    get_fonts_dir,
    resolve_devanagari_font,
    check_raqm_support,
)

__all__ = [
    "normalize_devanagari",
    "contains_devanagari",
    "split_graphemes",
    "grapheme_len",
    "wrap_indic_text",
    "get_fonts_dir",
    "resolve_devanagari_font",
    "check_raqm_support",
]
