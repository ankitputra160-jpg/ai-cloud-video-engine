"""
engine/text/pronunciation.py - Dual-Layer Speak-vs-Show Span-ID & Pre-TTS Normalizer
Converts numbers, currency (₹500 Cr), percentages (45%), years (2026), and English/acronyms
(Supreme Court, CJI, NASA) into pure phonetic Devanagari for IndicF5 & ctc-forced-aligner,
while keeping compact Hinglish/numeric `show` spans intact and chunk-locked for subtitles.
"""
import re
from typing import Any, Dict, List, Tuple

from engine.text.devanagari import normalize_devanagari
from engine.text.humanizer import strip_inline_tags

# Complete authentic Hindi number words (0-99) so numbers never stumble in Hindi TTS
_HINDI_0_TO_99: Tuple[str, ...] = (
    "शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चौवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
)

ENGLISH_TO_DEVANAGARI: Dict[str, str] = {
    "supreme court": "सुप्रीम कोर्ट",
    "high court": "हाई कोर्ट",
    "supreme": "सुप्रीम",
    "court": "कोर्ट",
    "cji": "सी जे आई",
    "bjp": "बी जे पी",
    "congress": "कांग्रेस",
    "election commission": "इलेक्शन कमीशन",
    "evm": "ई वी एम",
    "rti": "आर टी आई",
    "fir": "एफ आई आर",
    "cbi": "सी बी आई",
    "ed": "ई डी",
    "pib": "पी आई बी",
    "nasa": "नासा",
    "isro": "इसरो",
    "ai": "ए आई",
    "gpu": "जी पी यू",
    "cpu": "सी पी यू",
    "gdp": "जी डी पी",
    "ceo": "सी ई ओ",
    "dna": "डी एन ए",
    "usa": "यू एस ए",
    "uk": "यू के",
    "un": "यू एन",
    "pm": "पी एम",
    "cm": "सी एम",
    "mp": "एम पी",
    "mla": "एम एल ए",
    "dr": "डॉक्टर",
    "mr": "मिस्टर",
    "scandal": "स्कैंडल",
    "protest": "प्रोटेस्ट",
    "report": "रिपोर्ट",
    "data": "डेटा",
    "system": "सिस्टम",
    "record": "रिकॉर्ड",
    "government": "गवर्नमेंट",
    "ministry": "मिनिस्ट्री",
    "parliament": "पार्लियामेंट",
    "election": "इलेक्शन",
    "commission": "कमीशन",
    "police": "पोलिस",
    "nvidia": "एनवीडिया",
    "youtube": "यूट्यूब",
    "google": "गूगल",
    "whatsapp": "व्हाट्सएप",
    "skype": "स्काइप",
    "twitter": "ट्विटर",
    "trai": "ट्राई",
    "dot": "डी ओ टी",
    "mha": "एम एच ए",
    "i4c": "आई फोर सी",
    "rbi": "आर बी आई",
    "cyber": "साइबर",
    "cybercrime": "साइबर क्राइम",
    "digital": "डिजिटल",
    "arrest": "अरेस्ट",
    "digital arrest": "डिजिटल अरेस्ट",
    "cloning": "क्लोनिंग",
    "voice": "वॉइस",
    "scam": "स्कैम",
    "narcotics": "नारकोटिक्स",
    "customs": "कस्टम्स",
    "money": "मनी",
    "laundering": "लॉन्ड्रिंग",
    "video": "वीडियो",
    "call": "कॉल",
    "ludhiana": "लुधियाना",
    "livelaw": "लाइवलॉ",
    "media": "मीडिया",
    "viral": "वायरल",
    "breaking": "ब्रेकिंग",
    "news": "न्यूज़",
    "live": "लाइव",
    "cr": "करोड़",
    "crore": "करोड़",
    "lakh": "लाख",
    "lac": "लाख",
    "million": "मिलियन",
    "billion": "बिलियन",
}

_LETTER_PHONETICS = {
    "A": "ए", "B": "बी", "C": "सी", "D": "डी", "E": "ई", "F": "एफ", "G": "जी",
    "H": "एच", "I": "आई", "J": "जे", "K": "के", "L": "एल", "M": "एम", "N": "एन",
    "O": "ओ", "P": "पी", "Q": "क्यू", "R": "आर", "S": "एस", "T": "टी", "U": "यू",
    "V": "वी", "W": "डब्ल्यू", "X": "एक्स", "Y": "वाई", "Z": "ज़ेड",
}

_DIGRAPH_MAP = (
    ("tion", "शन"), ("sion", "ज़न"), ("sh", "श"), ("ch", "च"), ("th", "थ"),
    ("ph", "फ"), ("oo", "ऊ"), ("ee", "ई"), ("ea", "ई"), ("ai", "ऐ"),
    ("ay", "ए"), ("ow", "ओ"), ("ou", "आउ"), ("ng", "ंग"), ("ck", "क"),
)
_CHAR_MAP = {
    "a": "अ", "b": "ब", "c": "क", "d": "ड", "e": "ए", "f": "फ", "g": "ग",
    "h": "ह", "i": "इ", "j": "ज", "k": "क", "l": "ल", "m": "म", "n": "न",
    "o": "ओ", "p": "प", "q": "क", "r": "र", "s": "स", "t": "ट", "u": "उ",
    "v": "व", "w": "व", "x": "क्स", "y": "य", "z": "ज़",
}


def integer_to_hindi_words(n: int, as_year: bool = False) -> str:
    """Convert non-negative integers (up to crores/arabs) into natural spoken Hindi words."""
    if n < 0:
        return "माइनस " + integer_to_hindi_words(abs(n))
    if n < 100:
        return _HINDI_0_TO_99[n]

    # Spoken Indian year format (1947 -> उन्नीस सौ सैंतालीस; 2000-2099 -> दो हज़ार ...)
    if as_year and 1100 <= n <= 1999:
        hundreds = n // 100
        rem = n % 100
        res = f"{_HINDI_0_TO_99[hundreds]} सौ"
        if rem:
            res += f" {_HINDI_0_TO_99[rem]}"
        return res

    parts: List[str] = []
    if n >= 100_000_00:  # >= 1 Crore
        crores = n // 10_000_000
        parts.append(f"{integer_to_hindi_words(crores)} करोड़")
        n %= 10_000_000
    if n >= 100_000:  # Lakh
        lakhs = n // 100_000
        parts.append(f"{integer_to_hindi_words(lakhs)} लाख")
        n %= 100_000
    if n >= 1000:  # Thousand
        thousands = n // 1000
        parts.append(f"{integer_to_hindi_words(thousands)} हज़ार")
        n %= 1000
    if n >= 100:
        hundreds = n // 100
        parts.append(f"{_HINDI_0_TO_99[hundreds]} सौ")
        n %= 100
    if n > 0:
        parts.append(_HINDI_0_TO_99[n])
    return " ".join(parts)


def number_str_to_hindi(num_str: str, is_year: bool = False) -> str:
    """Convert numeric strings including commas and decimals (18.5 -> अठारह दशमलव पाँच)."""
    cleaned = num_str.replace(",", "").strip()
    if "." in cleaned:
        int_part, dec_part = cleaned.split(".", 1)
        left = integer_to_hindi_words(int(int_part or 0))
        right = " ".join(_HINDI_0_TO_99[int(d)] for d in dec_part if d.isdigit())
        return f"{left} दशमलव {right}".strip() if right else left
    val = int(cleaned or 0)
    likely_year = is_year or (1800 <= val <= 2099 and "," not in num_str)
    return integer_to_hindi_words(val, as_year=likely_year)


def english_word_to_devanagari(word: str) -> str:
    """Convert any English word or acronym into speakable Devanagari."""
    clean = re.sub(r"[^A-Za-z]", "", word)
    if not clean:
        return word
    low = clean.lower()
    if low in ENGLISH_TO_DEVANAGARI:
        return ENGLISH_TO_DEVANAGARI[low]
    if clean.isupper() and 2 <= len(clean) <= 5:
        return " ".join(_LETTER_PHONETICS.get(ch, ch) for ch in clean)

    # Lightweight phonetic syllable transliteration fallback
    out: List[str] = []
    i = 0
    while i < len(low):
        matched = False
        for dg, dv in _DIGRAPH_MAP:
            if low.startswith(dg, i):
                out.append(dv)
                i += len(dg)
                matched = True
                break
        if not matched:
            out.append(_CHAR_MAP.get(low[i], low[i]))
            i += 1
    return "".join(out)


# Multi-word & special patterns grouped as single non-breakable display spans
_GROUP_TOKEN_RE = re.compile(
    r"(?:₹|Rs\.?\s*)?\d[\d,]*(?:\.\d+)?\s*(?:Cr|Crore|Lakh|Lac|करोड़|लाख)\b"
    r"|\d[\d,]*(?:\.\d+)?%"
    r"|(?:₹|Rs\.?\s*)\d[\d,]*(?:\.\d+)?"
    r"|\b(?:Supreme\s+Court|High\s+Court|Election\s+Commission|Social\s+Media)\b"
    r"|\b\d[\d,]*(?:\.\d+)?\b"
    r"|\b[A-Za-z][A-Za-z.]*\b",
    flags=re.IGNORECASE,
)


def _convert_grouped_token_to_speak(token: str) -> str:
    """Turn one grouped display token (e.g. '₹500 Cr', '45%', '2026', 'Supreme Court') into spoken Devanagari."""
    t = token.strip()
    low = t.lower()

    if low in ENGLISH_TO_DEVANAGARI:
        return ENGLISH_TO_DEVANAGARI[low]

    # Currency + Cr/Lakh (e.g. "₹500 Cr", "500 करोड़")
    m_cur = re.match(
        r"^(?P<sym>₹|Rs\.?\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>Cr|Crore|Lakh|Lac|करोड़|लाख)$",
        t,
        flags=re.IGNORECASE,
    )
    if m_cur:
        num_words = number_str_to_hindi(m_cur.group("num"), is_year=False)
        unit_low = m_cur.group("unit").lower()
        unit_hi = "करोड़" if unit_low in ("cr", "crore", "करोड़") else "लाख"
        suffix = " रुपये" if m_cur.group("sym") else ""
        return f"{num_words} {unit_hi}{suffix}".strip()

    # Percentage (e.g. "45%", "18.5%")
    m_pct = re.match(r"^(\d[\d,]*(?:\.\d+)?)%$", t)
    if m_pct:
        return f"{number_str_to_hindi(m_pct.group(1), is_year=False)} परसेंट"

    # Plain ₹ amount ("₹500")
    m_rs = re.match(r"^(?:₹|Rs\.?\s*)(\d[\d,]*(?:\.\d+)?)$", t, flags=re.IGNORECASE)
    if m_rs:
        return f"{number_str_to_hindi(m_rs.group(1), is_year=False)} रुपये"

    # Multi-word English entities
    if " " in t:
        return " ".join(english_word_to_devanagari(p) for p in t.split())

    # Plain digits / year (special case for 1930 National Cyber Crime Helpline)
    if t == "1930":
        return "उन्नीस तीस"
    if re.fullmatch(r"\d[\d,]*(?:\.\d+)?", t):
        return number_str_to_hindi(t)

    # Plain English word / acronym (or Dr.)
    return english_word_to_devanagari(t)


def to_tts_tagged_text(tagged_text: str) -> str:
    """Normalize text for TTS while keeping [pause:Xs] and [emotion]...[/emotion] markup intact."""
    if not tagged_text:
        return ""
    tag_re = re.compile(r"(\[/?[a-zA-Z0-9_:.]+\])")
    parts = tag_re.split(tagged_text)
    out: List[str] = []
    for part in parts:
        if not part:
            continue
        if tag_re.fullmatch(part):
            out.append(part)
        else:
            converted = _GROUP_TOKEN_RE.sub(lambda m: _convert_grouped_token_to_speak(m.group(0)), part)
            out.append(normalize_devanagari(converted))
    return re.sub(r"\s+", " ", " ".join(out)).replace(" [/", "[/").strip()


def build_speak_show_alignment_spec(tagged_text: str) -> Dict[str, Any]:
    """Build synchronized Dual-Layer metadata:

    - tts_tagged_text: Devanagari text with inline [pause]/[emotion] tags for expressive TTS
    - speak_words: Ordered list of bare Devanagari words fed to ctc-forced-aligner (mms-300m)
    - display_spans: List of {span_id, show, speak_words, speak_start_idx, speak_end_idx}
      ensuring compound spans like '₹500 Cr' or 'Supreme Court' never split across subtitle lines.
    """
    tts_tagged = to_tts_tagged_text(tagged_text)
    plain_display = strip_inline_tags(tagged_text)

    # Walk plain_display preserving grouped spans as single units, splitting rest on whitespace
    raw_units: List[str] = []
    cursor = 0
    for m in _GROUP_TOKEN_RE.finditer(plain_display):
        if m.start() > cursor:
            between = plain_display[cursor:m.start()].strip()
            if between:
                raw_units.extend(tok for tok in between.split(" ") if tok)
        raw_units.append(m.group(0).strip())
        cursor = m.end()
    if cursor < len(plain_display):
        tail = plain_display[cursor:].strip()
        if tail:
            raw_units.extend(tok for tok in tail.split(" ") if tok)

    # Merge any trailing punctuation orphaned onto a previous grouped unit (e.g., '2026' + '।')
    merged_units: List[str] = []
    for u in raw_units:
        if merged_units and re.fullmatch(r"[।,.?!;:\"'”’)\]]+", u):
            merged_units[-1] = merged_units[-1] + u
        else:
            merged_units.append(u)

    speak_words: List[str] = []
    display_spans: List[Dict[str, Any]] = []

    for idx, show_unit in enumerate(merged_units):
        # Strip trailing punctuation when deriving alignable speak words
        core_for_speak = re.sub(r"[।,.?!;:\"'“”‘’()]+", "", show_unit).strip()
        if not core_for_speak:
            continue
        if _GROUP_TOKEN_RE.fullmatch(core_for_speak):
            spoken_phrase = _convert_grouped_token_to_speak(core_for_speak)
        else:
            spoken_phrase = _GROUP_TOKEN_RE.sub(
                lambda m: _convert_grouped_token_to_speak(m.group(0)), core_for_speak
            )
        spoken_phrase = normalize_devanagari(spoken_phrase)
        w_list = [w for w in spoken_phrase.split(" ") if w]
        if not w_list:
            continue

        start_idx = len(speak_words)
        speak_words.extend(w_list)
        end_idx = len(speak_words) - 1

        display_spans.append({
            "span_id": f"span_{len(display_spans) + 1}",
            "show": normalize_devanagari(show_unit),
            "speak_words": w_list,
            "speak_start_idx": start_idx,
            "speak_end_idx": end_idx,
        })

    return {
        "tts_tagged_text": tts_tagged,
        "plain_speak_text": " ".join(speak_words),
        "speak_words": speak_words,
        "display_spans": display_spans,
    }
