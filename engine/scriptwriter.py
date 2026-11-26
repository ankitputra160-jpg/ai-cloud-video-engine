"""
engine/scriptwriter.py - Stage B: Long-Form Documentary & 2D Video Scriptwriter
Supports 10s shorts up to 25-minute (1500s) multi-chapter documentaries and 2D Animation scripts
in Hindi (Devanagari NFC-normalized) and English.
"""
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from engine.research import ResearchDossier
from engine.text.devanagari import contains_devanagari, normalize_devanagari

logger = logging.getLogger("scriptwriter")

_2D_STYLE_PREFIX = (
    "vibrant 2D animated documentary illustration, clean editorial vector & cel-shading style, "
    "bold crisp linework, warm cinematic color grading, textured paper backdrop, 16:9 widescreen"
)

@dataclass
class ScriptChapter:
    chapter_index: int
    title: str
    narration: str
    target_seconds: float
    mood: str
    visual_intent: str
    layout: str = "hero"
    camera: str = "push_in"
    on_screen_date: str = ""
    visual_prompt_2d: str = ""

@dataclass
class DocumentaryScript:
    topic: str
    language: str
    target_duration: int
    title: str
    hook: str
    chapters: List[ScriptChapter] = field(default_factory=list)
    conclusion: str = ""
    estimated_duration: float = 0.0
    style: str = "Documentary"
    english_title: str = ""

    @property
    def total_words(self) -> int:
        full_text = " ".join([ch.narration for ch in self.chapters])
        return len(full_text.split())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "english_title": self.english_title or self.title,
            "language": self.language,
            "style": self.style,
            "target_duration": self.target_duration,
            "title": self.title,
            "hook": self.hook,
            "chapters": [
                {
                    "index": ch.chapter_index,
                    "title": ch.title,
                    "narration": ch.narration,
                    "target_seconds": ch.target_seconds,
                    "mood": ch.mood,
                    "visual_intent": ch.visual_intent,
                    "layout": ch.layout,
                    "camera": ch.camera,
                    "on_screen_date": ch.on_screen_date,
                    "visual_prompt_2d": ch.visual_prompt_2d,
                }
                for ch in self.chapters
            ],
            "conclusion": self.conclusion,
            "total_words": self.total_words,
            "estimated_duration": self.estimated_duration,
        }

    def to_2d_markdown(self) -> str:
        """Render the script as a human-readable 2D Animation Production Script & Prompt Sheet."""
        lines = [
            f"# 🎬 2D Production Script: {self.title}",
            f"- **Topic:** {self.topic} | **Language:** {self.language} | **Style:** {self.style}",
            f"- **Target Duration:** {self.target_duration}s ({len(self.chapters)} scenes, ~{self.total_words} words)\n",
            "---\n",
        ]
        for ch in self.chapters:
            tag = f"#{ch.chapter_index:03d}_scene_{ch.chapter_index:03d}"
            lines.extend([
                f"### Scene {ch.chapter_index}: {ch.title} (`{tag}`)",
                f"- **Duration:** {ch.target_seconds:.1f}s | **Layout:** `{ch.layout}` | **Camera:** `{ch.camera}` | **Mood:** `{ch.mood}`",
                f"- **On-Screen Overlay:** {ch.on_screen_date or 'None'}",
                f"- **Story Line ({len(ch.narration.split())} words):** {ch.narration}",
                f"- **2D Visual Prompt:**\n```text\n{tag} {ch.visual_prompt_2d or ch.visual_intent}\n```\n",
            ])
        return "\n".join(lines)


class ScriptWriter:
    LAYOUTS = ("hero", "split", "hero_r", "timeline", "quote", "board")
    CAMERAS = ("push_in", "pan_right", "pull_out", "pan_left", "drift")

    def __init__(
        self,
        language: str = "en",
        words_per_minute: int = 135,
        style: str = "Documentary",
        gemini_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
    ):
        self.language = language
        self.words_per_sec = words_per_minute / 60.0
        self.style = style
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "").strip() or None
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY", "").strip() or None

    def generate_script(self, dossier: ResearchDossier, target_duration: int) -> DocumentaryScript:
        """Dynamically compose a structured script scaled cleanly from 10s up to 25 minutes (1500s)."""
        if target_duration <= 15:
            num_scenes = 2
        elif target_duration <= 35:
            num_scenes = 3
        elif target_duration <= 90:
            num_scenes = max(4, round(target_duration / 15))
        else:
            # Long-form up to 25 min (1500s): ~12-14s per visual beat -> up to 120 scenes
            num_scenes = min(120, max(6, round(target_duration / 13)))

        seconds_per_scene = target_duration / num_scenes

        # Optional LLM enhancement if user provided Gemini/Groq free key (capped cleanly for reliability)
        if (self.gemini_api_key or self.groq_api_key) and num_scenes <= 30:
            llm_script = self._try_llm_script(dossier, target_duration, num_scenes, seconds_per_scene)
            if llm_script:
                return llm_script

        if self.language == "hi":
            return self._generate_hindi_script(dossier, target_duration, num_scenes, seconds_per_scene)
        return self._generate_english_script(dossier, target_duration, num_scenes, seconds_per_scene)

    def _try_llm_script(
        self, dossier: ResearchDossier, target_duration: int, num_scenes: int, sec_per_scene: float
    ) -> Optional[DocumentaryScript]:
        """Optional LLM script synthesis using free-tier Gemini or Groq APIs."""
        lang_label = "Hindi (Devanagari script)" if self.language == "hi" else "English"
        facts_block = "\n".join(f"- {f}" for f in dossier.key_facts[:16])
        prompt = (
            f"Write a {num_scenes}-scene documentary script in {lang_label} about '{dossier.topic}'. "
            f"Style: {self.style}. Each scene should have 20-30 spoken words, verified facts only.\n"
            f"Verified Facts:\n{facts_block}\n\n"
            f"Return JSON array of objects with keys: title, narration, visual_prompt, mood, on_screen_date."
        )
        try:
            raw_json = None
            if self.groq_api_key:
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps({
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.6,
                    }).encode("utf-8"),
                    headers={"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    raw_json = payload["choices"][0]["message"]["content"]
            elif self.gemini_api_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    raw_json = payload["candidates"][0]["content"]["parts"][0]["text"]

            if not raw_json:
                return None
            match = re.search(r"\[.*\]", raw_json, re.DOTALL)
            if not match:
                return None
            items = json.loads(match.group(0))
            if not isinstance(items, list) or len(items) < 2:
                return None

            chapters: List[ScriptChapter] = []
            exact_dur = target_duration / len(items)
            for idx, item in enumerate(items[:num_scenes]):
                narr = normalize_devanagari(str(item.get("narration", "")).strip())
                if not narr:
                    continue
                vprompt = str(item.get("visual_prompt", dossier.english_title or dossier.topic))
                chapters.append(ScriptChapter(
                    chapter_index=idx + 1,
                    title=normalize_devanagari(str(item.get("title", f"Scene {idx + 1}"))),
                    narration=narr,
                    target_seconds=exact_dur,
                    mood=str(item.get("mood", "curious")).lower(),
                    visual_intent=vprompt,
                    layout=self.LAYOUTS[idx % len(self.LAYOUTS)],
                    camera=self.CAMERAS[idx % len(self.CAMERAS)],
                    on_screen_date=str(item.get("on_screen_date", "")),
                    visual_prompt_2d=f"{_2D_STYLE_PREFIX}, {vprompt}",
                ))
            if len(chapters) >= 2:
                return DocumentaryScript(
                    topic=dossier.topic,
                    english_title=dossier.english_title or dossier.title,
                    language=self.language,
                    style=self.style,
                    target_duration=target_duration,
                    title=dossier.title,
                    hook=chapters[0].narration,
                    chapters=chapters,
                    conclusion=chapters[-1].narration,
                    estimated_duration=sum(ch.target_seconds for ch in chapters),
                )
        except Exception as e:
            logger.debug(f"Optional LLM script generation skipped, using deterministic engine: {e}")
        return None

    def _build_2d_prompt(self, subject: str, intent: str, date_tag: str) -> str:
        date_note = f", era caption '{date_tag}'" if date_tag else ""
        return f"{_2D_STYLE_PREFIX}, depicting {subject}: {intent}{date_note}, no text distortion"

    def _generate_english_script(
        self, dossier: ResearchDossier, target_duration: int, num_chapters: int, sec_per_ch: float
    ) -> DocumentaryScript:
        facts = dossier.key_facts or [dossier.summary]
        timeline = dossier.timeline or []
        entities = dossier.entities or [dossier.english_title or dossier.title]

        chapter_types = [
            ("The Awakening", "mysterious", "Atmospheric wide opening scene with dramatic light contrast"),
            ("Uncovering the Roots", "curious", "Historical manuscripts, early blueprints, detailed close-ups"),
            ("The Turning Point", "intense", "Dynamic historical breakthrough, rapid motion and energy"),
            ("Mastery and Craft", "focused", "Precision instruments, diagrams, methodical craftsmanship"),
            ("Deep Exploration", "curious", "Cross-section diagram, map trajectories and key milestones"),
            ("The Revelation", "inspiring", "Golden hour cinematic reveal of grand achievement"),
            ("Legacy and Tomorrow", "epic", "Sweeping panoramic horizon celebrating enduring influence"),
        ]
        varied_bridges = [
            "Archival records reveal a pivotal chapter:",
            "Closer investigation uncovers a remarkable milestone:",
            "Historical evidence highlights how this breakthrough unfolded:",
            "Researchers traced this transformation directly to a key insight:",
            "Across decades of observation, one pattern stood above the rest:",
            "This development reshaped conventional understanding:",
        ]

        chapters: List[ScriptChapter] = []
        subject = dossier.english_title or dossier.title

        for i in range(num_chapters):
            ch_meta = chapter_types[i % len(chapter_types)]
            target_words = max(10, min(35, int(sec_per_ch * self.words_per_sec)))
            date_tag = timeline[i % len(timeline)]["year"] if timeline and (i % 2 == 1) else ""
            entity = entities[i % len(entities)]

            if i == 0:
                narration = (
                    f"Across time and history, few subjects captivate human curiosity like {dossier.title}. "
                    f"What began as an extraordinary endeavor would permanently reshape our world."
                )
            elif i == num_chapters - 1:
                narration = (
                    f"Today, the enduring legacy of {dossier.title} stands as a testament to curiosity, "
                    f"precision, and timeless human ambition."
                )
            else:
                fact_piece = facts[(i - 1) % len(facts)].strip()
                if not fact_piece.endswith((".", "!", "?")):
                    fact_piece += "."
                bridge = varied_bridges[(i - 1) % len(varied_bridges)]
                narration = f"{bridge} {fact_piece}"

            narration = self._fit_narration_words(narration, target_words)
            v_intent = f"{ch_meta[2]} featuring {entity}"

            chapters.append(ScriptChapter(
                chapter_index=i + 1,
                title=f"{ch_meta[0]}" if num_chapters <= 7 else f"{ch_meta[0]} ({i + 1})",
                narration=narration,
                target_seconds=sec_per_ch,
                mood=ch_meta[1],
                visual_intent=v_intent,
                layout=self.LAYOUTS[i % len(self.LAYOUTS)],
                camera=self.CAMERAS[i % len(self.CAMERAS)],
                on_screen_date=date_tag,
                visual_prompt_2d=self._build_2d_prompt(subject, v_intent, date_tag),
            ))

        hook = chapters[0].narration.split(".")[0] + "."
        conclusion = chapters[-1].narration

        return DocumentaryScript(
            topic=dossier.topic,
            english_title=subject,
            language="en",
            style=self.style,
            target_duration=target_duration,
            title=dossier.title,
            hook=hook,
            chapters=chapters,
            conclusion=conclusion,
            estimated_duration=sum(ch.target_seconds for ch in chapters),
        )

    def _generate_hindi_script(
        self, dossier: ResearchDossier, target_duration: int, num_chapters: int, sec_per_ch: float
    ) -> DocumentaryScript:
        chapter_types = [
            ("शुरुआत का रहस्य", "mysterious", "Atmospheric night horizon and dramatic title illumination"),
            ("इतिहास और संदर्भ", "curious", "Ancient manuscripts, archival maps and historical engravings"),
            ("संघर्ष और मोड़", "intense", "Dynamic breakthrough movement, sparks and dramatic lighting"),
            ("कारीगरी और विज्ञान", "focused", "Precision instruments, geometric charts and technical detail"),
            ("खोज की गहराई", "curious", "Animated 2D diagrams, timeline progression and key entities"),
            ("भव्य प्रकटीकरण", "inspiring", "Golden cinematic reveal celebrating monumental discovery"),
            ("अमिट विरासत", "epic", "Panoramic vista reflecting lasting impact on future generations"),
        ]

        hindi_facts = [f for f in dossier.key_facts if contains_devanagari(f)]
        english_facts = [f for f in dossier.key_facts if not contains_devanagari(f)]
        timeline = dossier.timeline or []
        entities = dossier.entities or [dossier.english_title or dossier.title]

        varied_hindi_frames = [
            "ऐतिहासिक प्रमाण बताते हैं कि {subject} का यह चरण ज्ञान और शोध की दिशा बदलने वाला साबित हुआ।",
            "गहन अध्ययन से यह सामने आया कि उस दौर के विद्वानों ने सटीक गणना और सूक्ष्म अवलोकन से नई राह बनाई।",
            "दस्तावेज़ों और प्राचीन ग्रंथों में {subject} से जुड़े अनोखे सिद्धांतों और प्रयोगों का स्पष्ट उल्लेख मिलता है।",
            "समय के साथ इन खोजों ने न केवल विज्ञान को नई गति दी, बल्कि पूरी दुनिया की समझ को भी प्रभावित किया।",
            "विशेषज्ञों के अनुसार {subject} की सबसे बड़ी विशेषता इसकी सटीकता और व्यावहारिक सोच थी।",
            "यही वजह है कि सदियों बाद भी {subject} की तकनीक और विचार शोधकर्ताओं को प्रेरित करते हैं।",
        ]

        chapters: List[ScriptChapter] = []
        subject = dossier.title
        eng_subject = dossier.english_title or dossier.title

        for i in range(num_chapters):
            ch_meta = chapter_types[i % len(chapter_types)]
            target_words = max(12, min(35, int(sec_per_ch * self.words_per_sec)))
            date_tag = timeline[i % len(timeline)]["year"] if timeline and (i % 2 == 1) else ""
            entity = entities[i % len(entities)]

            if i == 0:
                narration = (
                    f"इतिहास के पन्नों में {subject} की कहानी हमेशा से इंसानी हौसले और जिज्ञासा का बेजोड़ प्रतीक रही है।"
                )
            elif i == num_chapters - 1:
                narration = (
                    f"आज {subject} की यह अमिट विरासत आने वाली पीढ़ियों के लिए लगन, ज्ञान और नएपन की अमर दास्तान बन चुकी है।"
                )
            elif hindi_facts and (i - 1) < len(hindi_facts):
                narration = hindi_facts[i - 1]
            else:
                frame = varied_hindi_frames[(i - 1) % len(varied_hindi_frames)].format(subject=subject)
                if date_tag:
                    narration = f"वर्ष {date_tag} के आसपास {entity} से जुड़ा एक बड़ा मोड़ आया। {frame}"
                elif english_facts:
                    narration = f"{entity} के संदर्भ में, {frame}"
                else:
                    narration = frame

            narration = normalize_devanagari(self._fit_narration_words(narration, target_words))
            v_intent = f"{ch_meta[2]} featuring {entity}"

            chapters.append(ScriptChapter(
                chapter_index=i + 1,
                title=ch_meta[0] if num_chapters <= 7 else f"{ch_meta[0]} ({i + 1})",
                narration=narration,
                target_seconds=sec_per_ch,
                mood=ch_meta[1],
                visual_intent=v_intent,
                layout=self.LAYOUTS[i % len(self.LAYOUTS)],
                camera=self.CAMERAS[i % len(self.CAMERAS)],
                on_screen_date=date_tag,
                visual_prompt_2d=self._build_2d_prompt(eng_subject, v_intent, date_tag),
            ))

        return DocumentaryScript(
            topic=dossier.topic,
            english_title=eng_subject,
            language="hi",
            style=self.style,
            target_duration=target_duration,
            title=subject,
            hook=chapters[0].narration,
            chapters=chapters,
            conclusion=chapters[-1].narration,
            estimated_duration=sum(ch.target_seconds for ch in chapters),
        )

    def _fit_narration_words(self, text: str, target_words: int) -> str:
        words = text.split()
        if len(words) > target_words + 8:
            trimmed = " ".join(words[:target_words + 2])
            last_punct = max(trimmed.rfind("."), trimmed.rfind(","), trimmed.rfind("।"))
            if last_punct > 15:
                return trimmed[:last_punct + 1]
            ending = "।" if contains_devanagari(trimmed) else "."
            return trimmed + ending
        return text
