"""
engine/text/humanizer.py - Spoken Hindi/Hinglish Anti-AI Critic (Inspired by blader/humanizer)
Scans scripts for textbook/essay AI clichés ("महज़", "निष्कर्षतः", "सर्वविदित है", "Not just X but Y"),
enforces crisp micro-beats (<= 22 words), and rewrites stiff prose into spontaneous thinking-out-loud speech.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from engine.text.devanagari import normalize_devanagari

logger = logging.getLogger("text.humanizer")

# Ordered longest-first so multi-word AI clichés get replaced cleanly before single words
BOOKISH_HINDI_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    ("आने वाला वक्त ही बताएगा।", ""),
    ("आने वाला समय ही बताएगा।", ""),
    ("आने वाला वक्त ही बताएगा", ""),
    ("इस प्रकार हम देखते हैं कि", "मतलब साफ़ है,"),
    ("इस प्रकार हम देखते हैं", "मतलब साफ़ है"),
    ("अत्यंत महत्वपूर्ण है कि", "बहुत ज़रूरी बात यह है कि"),
    ("अत्यंत महत्वपूर्ण", "बहुत ज़रूरी"),
    ("गौरतलब है कि", "असली बात यह है कि"),
    ("सर्वविदित है कि", "सब जानते हैं कि"),
    ("सर्वविदित है", "सबको पता है"),
    ("चिंता का विषय", "बड़ी चिंता"),
    ("महत्वपूर्ण मोड़", "बड़ा मोड़"),
    ("अदालती टिप्पणी", "कोर्ट की बात"),
    ("निष्कर्षतः", "सीधी बात ये है"),
    ("अतः", "इसलिए"),
    ("महज़", "सिर्फ"),
    ("पुनरीक्षण", "जाँच"),
    ("समीक्षा", "जाँच"),
    ("अनियमितताओं", "गड़बड़ियों"),
    ("अनियमितता", "गड़बड़ी"),
    ("परिलक्षित", "साफ़ दिखता"),
    ("आधारशिला", "नींव"),
    ("दृष्टिकोण", "नज़रिया"),
    ("अमिट विरासत", "गहरी छाप"),
    ("अमर दास्तान", "कहानी"),
    ("बेजोड़ प्रतीक", "बड़ी मिसाल"),
    ("बेशुमार", "ढेरों"),
    ("व्यापक स्तर पर", "बड़े पैमाने पर"),
    ("अग्रणी भूमिका", "मुख्य रोल"),
)

CLICHE_STRUCTURES: Tuple[re.Pattern, ...] = (
    re.compile(r"यह\s+(?:सिर्फ|केवल)\s+[^।?!]{3,45}\s+नहीं[,\s]+बल्कि\s+", re.IGNORECASE),
    re.compile(r"न\s+केवल\s+[^।?!]{3,45}[,\s]+बल्कि\s+", re.IGNORECASE),
)

SPOKEN_CONNECTORS: Tuple[str, ...] = (
    "ज़रा सोचिए...",
    "असल में हुआ ये कि...",
    "अब यहीं पर असली पेंच फँसता है।",
    "लेकिन रुकिए...",
    "सीधी बात समझिए...",
)

SPOKEN_INTERRUPT_OPENERS: Tuple[str, ...] = (
    "अब ज़रा सोचिए — ",
    "लेकिन कहानी यहीं खत्म नहीं होती। ",
    "आखिर ऐसा हुआ क्यों? ",
    "यहीं पर असली खेल शुरू होता है — ",
)


def strip_inline_tags(text: str) -> str:
    """Remove [pause:0.5s] and [emotion]...[/emotion] markup tags cleanly."""
    if not text:
        return ""
    cleaned = re.sub(r"\[/?[a-zA-Z0-9_:.]+\]", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def audit_hindi_beat(text: str, max_spoken_words: int = 26) -> Dict[str, Any]:
    """Detect AI-writing tells, bookish Sanskritized words, or overly long sentences."""
    plain = strip_inline_tags(text)
    words = [w for w in plain.split() if w]

    matched_bookish: List[str] = []
    for phrase, _ in BOOKISH_HINDI_REPLACEMENTS:
        if phrase and phrase in plain:
            matched_bookish.append(phrase)

    matched_cliches: List[str] = []
    for pat in CLICHE_STRUCTURES:
        m = pat.search(plain)
        if m:
            matched_cliches.append(m.group(0).strip())

    too_long = len(words) > max_spoken_words
    score = max(0.0, 1.0 - 0.18 * len(matched_bookish) - 0.25 * len(matched_cliches) - (0.2 if too_long else 0.0))

    return {
        "word_count": len(words),
        "too_long": too_long,
        "bookish_words": matched_bookish,
        "cliche_patterns": matched_cliches,
        "naturalness_score": round(score, 2),
        "needs_rewrite": bool(matched_bookish or matched_cliches or too_long),
    }


def humanize_hindi_rule_based(
    text: str,
    add_connector: bool = False,
    beat_index: int = 0,
    max_words: int = 24,
) -> str:
    """Deterministic spoken-Hinglish cleanup: purge bookish AI vocabulary and enforce crisp rhythm."""
    if not text:
        return ""

    out = text
    for bad, good in BOOKISH_HINDI_REPLACEMENTS:
        if bad in out:
            out = out.replace(bad, good)

    # Break "यह सिर्फ X नहीं, बल्कि Y" negative parallelism into direct human contrast
    out = re.sub(
        r"यह\s+(?:सिर्फ|केवल)\s+([^।?!,]{3,45})\s+नहीं[,\s]+बल्कि\s+",
        r"यह \1 तो है ही — और साथ में ",
        out,
    )
    out = re.sub(
        r"न\s+केवल\s+([^।?!,]{3,45})[,\s]+बल्कि\s+",
        r"\1 तो था ही, और साथ ही ",
        out,
    )

    out = re.sub(r"\s+", " ", out).strip()
    if add_connector and not re.search(r"^(ज़रा सोचिए|अब|लेकिन|आखिर|असल में|यहीं|सीधी बात)", out):
        opener = SPOKEN_INTERRUPT_OPENERS[beat_index % len(SPOKEN_INTERRUPT_OPENERS)]
        out = f"{opener}[pause:0.35s] {out}"

    # Enforce spoken word budget without stripping emotion tags
    plain_words = strip_inline_tags(out).split()
    if len(plain_words) > max_words + 6:
        # Keep first complete sentence if multiple textbook sentences were crammed together
        parts = re.split(r"(?<=[।?!])\s+", out)
        kept: List[str] = []
        w_sum = 0
        for p in parts:
            pw = len(strip_inline_tags(p).split())
            if kept and (w_sum + pw > max_words + 4):
                break
            kept.append(p)
            w_sum += pw
        if kept:
            out = " ".join(kept).strip()

    # Ensure valid ending punctuation outside tags
    tail_stripped = re.sub(r"(\[/[a-z]+\])\s*$", "", out).strip()
    if tail_stripped and tail_stripped[-1] not in ("।", "?", "!", "."):
        if re.search(r"\[/[a-z]+\]\s*$", out):
            out = re.sub(r"(\[/[a-z]+\])\s*$", r"।\1", out)
        else:
            out += "।"

    return normalize_devanagari(out)


def humanize_with_critic_pass(
    text: str,
    llm_client: Optional[Any] = None,
    is_pattern_interrupt: bool = False,
    beat_index: int = 0,
) -> str:
    """Apply blader/humanizer Anti-AI Self-Audit pass (LLM when available + rule-based polish)."""
    rule_cleaned = humanize_hindi_rule_based(
        text,
        add_connector=is_pattern_interrupt,
        beat_index=beat_index,
    )
    audit = audit_hindi_beat(rule_cleaned)
    if llm_client is None or not audit["needs_rewrite"]:
        return rule_cleaned

    prompt = (
        "नीचे दी गई हिंदी डॉक्यूमेंट्री लाइन को पढ़कर बताओ इसमें क्या चीज़ किताब या AI जैसी लग रही है, "
        "और उसे ऐसे लिखो जैसे कोई इंसान कैमरे के सामने तुरंत सोचकर बोल रहा हो:\n"
        "- नियम: सिर्फ 8–18 शब्द, आम बोलचाल की Hinglish, 'महज़/निष्कर्षतः/अत्यंत/सर्वविदित' जैसे शब्द बिल्कुल नहीं।\n"
        "- केवल [pause:0.4s], [slow]...[/slow], [fear]...[/fear], [angry]...[/angry], [fast]...[/fast] में से अधिकतम 1 टैग रखें।\n"
        "- केवल बदली हुई एक लाइन वापस करें (कोई भूमिका नहीं)।\n\n"
        f"लाइन: {rule_cleaned}"
    )
    rewritten = llm_client.generate_text(prompt, temperature=0.5, max_tokens=160)
    if rewritten:
        cleaned = humanize_hindi_rule_based(rewritten.strip().strip('"').strip("'"), add_connector=False)
        if 4 <= len(strip_inline_tags(cleaned).split()) <= 26:
            return cleaned
    return rule_cleaned
