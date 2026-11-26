"""
engine/text - Unicode text normalization, Indic/Devanagari matra shaping, anti-AI Hindi humanizer,
and Dual-Layer Speak-vs-Show Span-ID pronunciation mapping.
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
from engine.text.humanizer import (
    audit_hindi_beat,
    humanize_hindi_rule_based,
    humanize_with_critic_pass,
    strip_inline_tags,
)
from engine.text.pronunciation import (
    build_speak_show_alignment_spec,
    integer_to_hindi_words,
    to_tts_tagged_text,
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
    "audit_hindi_beat",
    "humanize_hindi_rule_based",
    "humanize_with_critic_pass",
    "strip_inline_tags",
    "build_speak_show_alignment_spec",
    "integer_to_hindi_words",
    "to_tts_tagged_text",
]
