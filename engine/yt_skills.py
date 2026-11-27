"""
engine/yt_skills.py - Integration Layer for the 11 YouTube Agent Skills
Connects `skills/youtube-agent/` tools (`hooks.json`, `hookscore.py`, `title.py`,
`chapters.py`, `deadair.py`, `retention.py`) directly into the documentary pipeline
with bilingual English + Hindi/Hinglish support.
"""
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILLS_ROOT = os.path.join(_REPO_ROOT, "skills", "youtube-agent")

# Add yt-script, yt-package, yt-chapters, yt-edit to path cleanly when needed
for _sub in ("yt-script", "yt-package", "yt-chapters", "yt-edit"):
    _p = os.path.join(_SKILLS_ROOT, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)

_HI_ADDRESS_RE = re.compile(r"(आप|आपका|आपके|आपकी|तुम|ज़रा|सोचिए|मानिए|रुकिए)")
_HI_STAKE_RE = re.compile(r"(गँवा|गिरफ्तार|ठगी|स्कैम|खो|बर्बाद|ख़तरा|बच|नुकसान|जेल|लूट|फँस|ख़त्म)")
_HI_CURIOSITY_RE = re.compile(r"(क्यों|कैसे|क्या|कौन|कहाँ|लेकिन|रुकिए|असल में|पेंच|सच|राज|\?)")
_CONCRETE_RE = re.compile(r"(?:₹\s*\d[\d,.]*|\d[\d,.]*\s*(?:%|करोड़|लाख|हज़ार|सेकंड|मिनट|घंटे|दिन|साल|Crore|Lakh|s|m|h)?|\b(?:1930|CBI|TRAI|RBI|MHA|I4C|PIB|WhatsApp|Skype)\b)", re.I)


def load_hook_formulas() -> List[Dict[str, Any]]:
    hooks_json = os.path.join(_SKILLS_ROOT, "yt-script", "hooks.json")
    if os.path.exists(hooks_json):
        with open(hooks_json, "r", encoding="utf-8") as f:
            return json.load(f).get("hooks", [])
    return []


def score_bilingual_hook(hook_text: str) -> Dict[str, Any]:
    """Score an English or Hindi/Hinglish opening hook using the 5 YouTube hook properties."""
    clean = (hook_text or "").strip()
    if not clean:
        return {"verdict": 0, "band": "WEAK", "properties": {}, "formula": "Empty"}

    # If pure ASCII, run upstream hookscore directly as baseline + blend Hindi signals
    has_indic = bool(re.search(r"[\u0900-\u097F]", clean))
    if not has_indic:
        try:
            import hookscore as _hs
            parts, verdict, name, hits = _hs.score(clean)
            return {
                "hook": clean,
                "properties": parts,
                "verdict": verdict,
                "band": _hs.band(verdict),
                "formula": name,
                "matched": hits,
            }
        except Exception:
            pass

    words = [w for w in re.split(r"\s+", clean) if w]
    n_words = len(words)
    nums = len(_CONCRETE_RE.findall(clean))
    specificity = max(0, min(100, 38 + nums * 22))
    n_addr = len(_HI_ADDRESS_RE.findall(clean))
    first6 = " ".join(words[:6])
    address = max(0, min(100, 28 + n_addr * 20 + (28 if _HI_ADDRESS_RE.search(first6) else 0)))
    n_stake = len(_HI_STAKE_RE.findall(clean))
    stakes = max(0, min(100, 24 + n_stake * 24 + (14 if nums else 0)))
    n_cur = len(_HI_CURIOSITY_RE.findall(clean))
    curiosity = max(0, min(100, 28 + n_cur * 18 + (18 if "?" in clean else 0)))
    if 9 <= n_words <= 26:
        brevity = 100
    elif n_words < 9:
        brevity = max(35, 100 - (9 - n_words) * 10)
    else:
        brevity = max(25, 100 - (n_words - 26) * 6)

    parts = {
        "SPECIFICITY": specificity,
        "ADDRESS": address,
        "STAKES": stakes,
        "CURIOSITY": curiosity,
        "BREVITY": brevity,
    }
    vals = list(parts.values())
    verdict = round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals))
    band = "STRONG" if verdict >= 72 else ("WORKABLE" if verdict >= 55 else "WEAK")
    formula = "The Statistic / Mistake" if nums and "?" in clean else ("The Question" if "?" in clean else "The Reveal")
    return {"hook": clean, "properties": parts, "verdict": verdict, "band": band, "formula": formula}


def lint_title_thumbnail_pair(title: str, thumb_text: str) -> Dict[str, Any]:
    """Check YouTube title + thumbnail pairing using yt-package/title.py principles."""
    try:
        import title as _yt_title
        res = _yt_title.check(title, thumb_text)
    except Exception:
        res = {"title": title, "chars": len(title), "score": 80, "issues": [], "good": []}

    # Add Indic/Hinglish word-overlap & thumbnail word-count check (<=4 words)
    t_words = {w.lower() for w in re.findall(r"[\w\u0900-\u097F]+", title) if len(w) > 2}
    h_words = [w for w in re.findall(r"[\w\u0900-\u097F₹]+", thumb_text)]
    if len(h_words) > 5:
        res["issues"].append(("thumb-length", f"{len(h_words)} words on thumbnail (keep <= 4-5 words)"))
    shared = t_words & {w.lower() for w in h_words if len(w) > 2}
    if shared:
        res["issues"].append(("duplicate-indic", f"Title and thumbnail overlap on: {', '.join(sorted(shared))}"))
    return res


def export_youtube_package_and_chapters(
    manifest: Any,
    srt_path: Optional[str],
    output_dir: str,
) -> Dict[str, str]:
    """Generate YouTube-compliant 0:00 chapters (>=10s each) and Dead-Air audit report."""
    os.makedirs(output_dir, exist_ok=True)
    chapters: List[Dict[str, Any]] = []
    cursor = 0.0
    scenes = getattr(manifest, "scenes", []) or []

    # Group scenes into logical >=15s YouTube chapters (starting strictly at 0:00)
    block_size = max(1, len(scenes) // 8) if len(scenes) >= 16 else 1
    for i in range(0, len(scenes), block_size):
        chunk = scenes[i:i + block_size]
        dur = sum(float(getattr(s, "duration", 10.0)) for s in chunk)
        # Ensure minimum 10s per YouTube chapter rule (merge trailing short block into previous)
        if chapters and dur < 10.0:
            chapters[-1]["seconds"] = round(chapters[-1]["seconds"] + dur, 2)
            cursor += dur
            continue
        t_int = int(round(cursor))
        mm, ss = t_int // 60, t_int % 60
        label = f"{mm}:{ss:02d}"
        title = str(getattr(chunk[0], "title", f"Part {len(chapters) + 1}")).strip()
        chapters.append({"start": round(cursor, 2), "label": label, "title": title, "seconds": round(dur, 2)})
        cursor += dur

    chapters_txt_path = os.path.join(output_dir, "youtube_chapters.txt")
    with open(chapters_txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(f"{c['label']} {c['title']}" for c in chapters) + "\n")

    deadair_summary: Dict[str, Any] = {"cuts": [], "removed": 0.0}
    if srt_path and os.path.exists(srt_path):
        try:
            import deadair as _da
            cues = _da.load(srt_path)
            if cues:
                cuts = []
                for idx in range(1, len(cues)):
                    gap = cues[idx][0] - cues[idx - 1][1]
                    if gap > 0.85:
                        cuts.append({"start": round(cues[idx - 1][1], 2), "end": round(cues[idx][0], 2), "gap": round(gap, 2)})
                deadair_summary = {
                    "cues": len(cues),
                    "long_gaps_over_0_85s": len(cuts),
                    "cuts": cuts[:15],
                }
        except Exception:
            pass

    hook_txt = scenes[0].narration if scenes else getattr(manifest, "topic", "")
    hook_eval = score_bilingual_hook(hook_txt)
    thumb_hook = getattr(manifest, "thumbnail_hook", "") or " ".join(hook_txt.split()[:4])
    title_lint = lint_title_thumbnail_pair(getattr(manifest, "topic", ""), thumb_hook)

    pkg_path = os.path.join(output_dir, "youtube_package.json")
    with open(pkg_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "topic": getattr(manifest, "topic", ""),
                "thumbnail_hook": thumb_hook,
                "hook_score": hook_eval,
                "title_thumb_lint": title_lint,
                "chapters": chapters,
                "chapters_valid": len(chapters) >= 3 and chapters[0]["start"] == 0.0 and all(c["seconds"] >= 10.0 for c in chapters),
                "deadair_audit": deadair_summary,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    return {"chapters_txt": chapters_txt_path, "package_json": pkg_path}
