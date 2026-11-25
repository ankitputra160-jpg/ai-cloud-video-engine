"""
engine/scriptwriter.py - Stage B: Documentary Scriptwriting & Narrative Structure
Generates engaging chaptered documentary scripts in English and Hindi.
"""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any
from engine.research import ResearchDossier

@dataclass
class ScriptChapter:
    chapter_index: int
    title: str
    narration: str
    target_seconds: float
    mood: str
    visual_intent: str

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

    @property
    def total_words(self) -> int:
        full_text = " ".join([ch.narration for ch in self.chapters])
        return len(full_text.split())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "language": self.language,
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
                    "visual_intent": ch.visual_intent
                }
                for ch in self.chapters
            ],
            "conclusion": self.conclusion,
            "total_words": self.total_words,
            "estimated_duration": self.estimated_duration
        }

class ScriptWriter:
    def __init__(self, language: str = "en", words_per_minute: int = 135):
        self.language = language
        self.words_per_sec = words_per_minute / 60.0

    def generate_script(self, dossier: ResearchDossier, target_duration: int) -> DocumentaryScript:
        """Dynamically compose a structured documentary script based on research facts and target length."""
        # Calculate target chapters based on duration
        # Minimum 2 chapters for short tests (<=15s), 3 for 30s, 4-5 for 60s, up to 8 for long form
        if target_duration <= 15:
            num_chapters = 2
        elif target_duration <= 35:
            num_chapters = 3
        elif target_duration <= 90:
            num_chapters = 4
        else:
            num_chapters = min(8, max(5, target_duration // 25))

        seconds_per_chapter = target_duration / num_chapters

        if self.language == "hi":
            return self._generate_hindi_script(dossier, target_duration, num_chapters, seconds_per_chapter)
        else:
            return self._generate_english_script(dossier, target_duration, num_chapters, seconds_per_chapter)

    def _generate_english_script(self, dossier: ResearchDossier, target_duration: int, num_chapters: int, sec_per_ch: float) -> DocumentaryScript:
        facts = dossier.key_facts
        summary_clean = re.sub(r'\[\d+\]', '', dossier.summary).strip()
        sentences = [s.strip() for s in summary_clean.split('.') if len(s.strip()) > 15]

        # Chapter templates with narrative arc
        chapter_types = [
            ("The Awakening", "mysterious", "Atmospheric wide opening shots with deep contrast"),
            ("Uncovering the Roots", "curious", "Historical footage, blueprints, close-up details"),
            ("The Turning Point", "intense", "Action, movement, sparks, mechanical motion, high energy"),
            ("Mastery and Craft", "focused", "Precision work, craftsmanship, tools and craftsmanship"),
            ("The Revelation", "inspiring", "Epic reveal, golden hour lighting, cinematic completion"),
            ("Legacy and Tomorrow", "epic", "Reflective pan shots, sweeping horizon, lingering grandeur")
        ]

        chapters: List[ScriptChapter] = []
        for i in range(num_chapters):
            ch_meta = chapter_types[i % len(chapter_types)]
            
            # Select relevant fact or sentence
            source_content = sentences[i % len(sentences)] if sentences else dossier.summary
            target_words = max(8, int(sec_per_ch * self.words_per_sec))

            if i == 0:
                narration = f"Across time and history, few subjects captivate human curiosity like {dossier.title}. What began as an extraordinary endeavor would redefine our perspective."
            elif i == num_chapters - 1:
                narration = f"Today, the legacy of {dossier.title} stands as a testament to ingenuity, perseverance, and timeless human ambition."
            elif i < len(facts) + 1 and facts:
                fact_piece = facts[(i - 1) % len(facts)]
                narration = f"Deep within its history lies a defining truth: {fact_piece}. Each detail marks a step toward mastering the impossible."
            else:
                narration = f"With every deliberate effort, {dossier.title} evolved beyond its initial boundaries, turning challenges into triumphant benchmarks."

            # Adjust narration length to target word count
            narration = self._fit_narration_words(narration, target_words)

            chapters.append(ScriptChapter(
                chapter_index=i + 1,
                title=ch_meta[0],
                narration=narration,
                target_seconds=sec_per_ch,
                mood=ch_meta[1],
                visual_intent=ch_meta[2]
            ))

        hook = chapters[0].narration.split('.')[0] + "."
        conclusion = chapters[-1].narration

        return DocumentaryScript(
            topic=dossier.topic,
            language="en",
            target_duration=target_duration,
            title=dossier.title,
            hook=hook,
            chapters=chapters,
            conclusion=conclusion,
            estimated_duration=sum(ch.target_seconds for ch in chapters)
        )

    def _generate_hindi_script(self, dossier: ResearchDossier, target_duration: int, num_chapters: int, sec_per_ch: float) -> DocumentaryScript:
        chapter_types = [
            ("शुरुआत का रहस्य", "mysterious", "वायुमंडलीय परिदृश्य और विहंगम दृश्य"),
            ("इतिहास और संदर्भ", "curious", "पुराने दस्तावेज़, रूपरेखा और निर्माण"),
            ("संघर्ष और मोड़", "intense", "परिश्रम, आग की चिंगारियां और तेज हलचल"),
            ("कारीगरी और समर्पण", "focused", "सटीक काम, औजारों का संतुलन और तकनीकी कौशल"),
            ("भव्य प्रकटीकरण", "inspiring", "शानदार अंतिम रूप और मनमोहक दृश्य"),
            ("अमिट विरासत", "epic", "भविष्य की प्रेरणा और यादगार प्रभाव")
        ]

        chapters: List[ScriptChapter] = []
        for i in range(num_chapters):
            ch_meta = chapter_types[i % len(chapter_types)]
            target_words = max(8, int(sec_per_ch * self.words_per_sec))

            if i == 0:
                narration = f"इतिहास के पन्नों में {dossier.title} की कहानी हमेशा से इंसानी हौसले और जिज्ञासा का बेजोड़ प्रतीक रही है।"
            elif i == num_chapters - 1:
                narration = f"आज {dossier.title} की यह मिसाल आने वाली पीढ़ियों के लिए लगन और नएपन की अमर दास्तान बन चुकी है।"
            else:
                narration = f"इसके विकास का हर चरण कठिन परिश्रम और अद्भुत सूझबूझ की गवाही देता है, जिसने असंभव को संभव बनाया।"

            narration = self._fit_narration_words(narration, target_words)

            chapters.append(ScriptChapter(
                chapter_index=i + 1,
                title=ch_meta[0],
                narration=narration,
                target_seconds=sec_per_ch,
                mood=ch_meta[1],
                visual_intent=ch_meta[2]
            ))

        return DocumentaryScript(
            topic=dossier.topic,
            language="hi",
            target_duration=target_duration,
            title=dossier.title,
            hook=chapters[0].narration,
            chapters=chapters,
            conclusion=chapters[-1].narration,
            estimated_duration=sum(ch.target_seconds for ch in chapters)
        )

    def _fit_narration_words(self, text: str, target_words: int) -> str:
        words = text.split()
        if len(words) > target_words + 8:
            # Trim neatly at sentence or comma
            trimmed = " ".join(words[:target_words + 2])
            last_punct = max(trimmed.rfind('.'), trimmed.rfind(','))
            if last_punct > 15:
                return trimmed[:last_punct + 1]
            return trimmed + "."
        return text
