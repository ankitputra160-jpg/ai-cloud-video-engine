"""
engine/scriptwriter.py - Module 3: 3-Pass Spontaneous Documentary & 2D Scriptwriter
Supports 10s shorts up to 25-minute (1500s) multi-chapter documentaries in conversational
Hindi/Hinglish and English without textbook AI phrasing.

3-Pass Pipeline:
  Pass 1: Fact-Sheet Grounded Chapter Batch Structure + 35-40s Pattern Interrupts
  Pass 2: Spontaneous Thinking-Out-Loud Draft + Inline [pause]/[emotion] Tags (<= 22 words/beat)
  Pass 3: HindiHumanizerCritic Audit + Speak/Show Dual-Layer Span-ID Normalization
"""
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.llm_client import UnifiedLLMClient
from engine.research import ResearchDossier
from engine.text.devanagari import contains_devanagari, normalize_devanagari
from engine.text.humanizer import humanize_hindi_rule_based, humanize_with_critic_pass, strip_inline_tags
from engine.text.pronunciation import build_speak_show_alignment_spec

logger = logging.getLogger("scriptwriter")

ANTI_VIRTUAL_PROMPT_SUFFIX = (
    "raw archival documentary photograph, shot on 35mm Leica lens, natural overcast daylight, "
    "subtle film grain, authentic texture, candid photojournalism, 16:9 widescreen"
)
ANTI_VIRTUAL_NEGATIVE_PROMPT = (
    "3d render, cgi, unreal engine, smooth plastic skin, neon lighting, glowing, "
    "symmetrical, cartoon, digital art, distorted text, watermark"
)
_2D_STYLE_PREFIX = (
    "vibrant 2D editorial documentary illustration, clean vector and textured paper style, "
    "bold crisp linework, warm archival color grading, 16:9 widescreen"
)


@dataclass
class ScriptChapter:
    chapter_index: int
    title: str
    narration: str  # Clean display text (tags stripped, compact 'show' format)
    target_seconds: float
    mood: str
    visual_intent: str
    layout: str = "hero"
    camera: str = "push_in"
    on_screen_date: str = ""
    visual_prompt_2d: str = ""
    tagged_narration: str = ""  # Inline [pause:0.4s], [fear], [angry], [slow], [fast]
    tts_text: str = ""  # Phonetic Devanagari + tags for IndicF5 / Parler-TTS
    speak_words: List[str] = field(default_factory=list)
    display_spans: List[Dict[str, Any]] = field(default_factory=list)
    visual_type: str = "real_photo"
    is_pattern_interrupt: bool = False
    is_archive_quote: bool = False
    news_headline: str = ""
    news_source: str = ""
    quote_speaker: str = ""


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
                    "tagged_narration": ch.tagged_narration or ch.narration,
                    "tts_text": ch.tts_text or ch.narration,
                    "speak_words": ch.speak_words,
                    "display_spans": ch.display_spans,
                    "target_seconds": ch.target_seconds,
                    "mood": ch.mood,
                    "visual_intent": ch.visual_intent,
                    "visual_type": ch.visual_type,
                    "is_pattern_interrupt": ch.is_pattern_interrupt,
                    "is_archive_quote": ch.is_archive_quote,
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
        """Render the script as a human-readable 2D & Documentary Production Script Sheet."""
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
                f"- **Duration:** {ch.target_seconds:.1f}s | **Visual:** `{ch.visual_type}` | **Layout:** `{ch.layout}` | **Camera:** `{ch.camera}` | **Mood:** `{ch.mood}`",
                f"- **On-Screen Overlay:** {ch.on_screen_date or 'None'}",
                f"- **Tagged Voice Script:** {ch.tagged_narration or ch.narration}",
                f"- **Screen Display ({len(ch.narration.split())} words):** {ch.narration}",
                f"- **Visual Prompt:**\n```text\n{tag} {ch.visual_prompt_2d or ch.visual_intent}\n```\n",
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
        hf_token: Optional[str] = None,
        llm_mode: str = "auto",
        llm_client: Optional[UnifiedLLMClient] = None,
    ):
        self.language = language
        self.words_per_sec = words_per_minute / 60.0
        self.style = style
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "").strip() or None
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY", "").strip() or None
        self.llm = llm_client or UnifiedLLMClient(
            llm_mode=llm_mode,
            gemini_api_key=self.gemini_api_key,
            groq_api_key=self.groq_api_key,
            hf_token=hf_token,
        )

    def generate_script(self, dossier: ResearchDossier, target_duration: int) -> DocumentaryScript:
        """Compose a grounded multi-beat script scaled cleanly from 10s up to 25 minutes (1500s)."""
        if target_duration <= 15:
            num_scenes = 2
        elif target_duration <= 35:
            num_scenes = 3
        elif target_duration <= 90:
            num_scenes = max(4, round(target_duration / 15))
        else:
            # Up to 25 min (1500s): 12-14s audio thought-blocks -> up to 120 scenes (300+ sub-cuts)
            num_scenes = min(120, max(6, round(target_duration / 13)))

        seconds_per_scene = target_duration / num_scenes

        if self.llm.is_llm_available():
            try:
                llm_script = self._generate_batched_llm_script(dossier, target_duration, num_scenes, seconds_per_scene)
                if llm_script:
                    return llm_script
            finally:
                # Stage-Gate VRAM discipline: unload local Gemma before audio/visual stages
                self.llm.unload()

        if self.language == "hi":
            return self._generate_hindi_script(dossier, target_duration, num_scenes, seconds_per_scene)
        return self._generate_english_script(dossier, target_duration, num_scenes, seconds_per_scene)

    def _generate_batched_llm_script(
        self,
        dossier: ResearchDossier,
        target_duration: int,
        num_scenes: int,
        sec_per_scene: float,
    ) -> Optional[DocumentaryScript]:
        """3-Pass Chapter-Batched Generation: works up to full 25 minutes (120 beats) without 429/cutoff."""
        batch_size = 12
        total_batches = math.ceil(num_scenes / batch_size)
        chapters: List[ScriptChapter] = []
        facts = dossier.key_facts or [dossier.summary]
        news_items = dossier.news_items or []
        quotes = dossier.verified_quotes or []
        prev_context = "Opening hook of the documentary."

        for b_idx in range(total_batches):
            start_i = b_idx * batch_size
            count = min(batch_size, num_scenes - start_i)
            fact_slice = facts[start_i % len(facts):] + facts[:start_i % len(facts)]
            fact_lines = "\n".join(f"- {f}" for f in fact_slice[:14])
            news_hint = ""
            if news_items:
                ni = news_items[b_idx % len(news_items)]
                news_hint = f"\nVerified News Headline: {ni.get('headline', '')} ({ni.get('source', '')}, {ni.get('date', '')})"

            is_opening = b_idx == 0
            is_ending = b_idx == total_batches - 1

            if self.language == "hi":
                prompt = (
                    f"Topic: {dossier.topic} ({dossier.english_title or dossier.title})\n"
                    f"Batch {b_idx + 1}/{total_batches} | Generate EXACTLY {count} conversational Hinglish spoken beats.\n"
                    f"Continuity context: {prev_context}\n"
                    f"Stage: {'Opening Hook (0-30s curiosity shock)' if is_opening else ('Conclusion' if is_ending else 'Deep Story Investigation')}\n"
                    f"Verified Fact Sheet ONLY (never invent fake dates):\n{fact_lines}{news_hint}\n\n"
                    "STRICT SPOKEN STYLE RULES:\n"
                    "1. Write like someone thinking out loud and explaining directly to a friend — NOT essay/book Hindi.\n"
                    "2. Each beat = 12 to 20 words max, natural short clauses. Every 3rd beat MUST be a Pattern Interrupt (question, contrast, or twist like 'ज़रा सोचिए...', 'लेकिन यहीं असली खेल शुरू होता है').\n"
                    "3. BAN bookish words: 'महज़', 'निष्कर्षतः', 'इस प्रकार', 'अत्यंत महत्वपूर्ण', 'सर्वविदित है', 'गौरतलब है कि', 'पुनरीक्षण'.\n"
                    "4. Use compact readable display forms on numbers/English terms: '₹500 Cr', '45%', '2026', 'Supreme Court', 'CJI'.\n"
                    "5. You may use AT MOST 1-2 tags per beat ONLY from: [pause:0.4s], [slow]...[/slow], [fear]...[/fear], [angry]...[/angry], [fast]...[/fast].\n"
                    "6. visual_prompt_en MUST be in crisp English for documentary photography/2D cards.\n\n"
                    'Return strictly a JSON object: {"beats": [{"title": "...", "tagged_narration": "...", "visual_prompt_en": "...", "scene_type": "real_photo|news_card|quote_card|map_card|ai_image", "mood": "mysterious|curious|intense|focused|epic", "on_screen_date": ""}]}'
                )
            else:
                prompt = (
                    f"Topic: {dossier.topic}\n"
                    f"Batch {b_idx + 1}/{total_batches} | Generate EXACTLY {count} engaging conversational documentary beats.\n"
                    f"Continuity: {prev_context}\n"
                    f"Verified Facts ONLY:\n{fact_lines}{news_hint}\n\n"
                    "RULES: 15-22 spoken words per beat, direct conversational storytelling, pattern interrupt question every 3rd beat, "
                    "max 1 tag from [pause:0.4s], [slow]...[/slow], [fear]...[/fear], [angry]...[/angry], [fast]...[/fast].\n"
                    'Return strictly JSON: {"beats": [{"title": "...", "tagged_narration": "...", "visual_prompt_en": "...", "scene_type": "real_photo|news_card|quote_card|map_card|ai_image", "mood": "mysterious|curious|intense|focused|epic", "on_screen_date": ""}]}'
                )

            payload = self.llm.generate_json(prompt, temperature=0.6, max_tokens=3600)
            items = None
            if isinstance(payload, dict):
                items = payload.get("beats") or payload.get("chapters") or payload.get("scenes")
            elif isinstance(payload, list):
                items = payload
            if not isinstance(items, list) or not items:
                return None

            for local_i in range(count):
                item = items[local_i % len(items)]
                global_i = start_i + local_i
                is_interrupt = (global_i % 3 == 0)
                raw_tagged = str(item.get("tagged_narration") or item.get("narration") or "").strip()
                if not raw_tagged:
                    continue

                if self.language == "hi":
                    # Pass 3: Anti-AI Critic Audit + Spoken Rewrite
                    raw_tagged = humanize_with_critic_pass(
                        raw_tagged,
                        llm_client=self.llm if local_i < 2 else None,
                        is_pattern_interrupt=is_interrupt,
                        beat_index=global_i,
                    )

                chap = self._finalize_chapter(
                    idx=global_i,
                    title=str(item.get("title", f"Beat {global_i + 1}")),
                    tagged_narration=raw_tagged,
                    target_seconds=sec_per_scene,
                    mood=str(item.get("mood", "curious")).lower(),
                    visual_intent=str(item.get("visual_prompt_en") or item.get("visual_prompt") or dossier.english_title or dossier.topic),
                    on_screen_date=str(item.get("on_screen_date", "")),
                    scene_type=str(item.get("scene_type", "real_photo")),
                    dossier=dossier,
                    is_interrupt=is_interrupt,
                    is_hero_hook=(global_i == 0 or global_i % 12 == 0),
                    quotes=quotes,
                    news_items=news_items,
                )
                chapters.append(chap)

            if chapters:
                prev_context = " ".join(c.narration for c in chapters[-2:])[:240]

        if len(chapters) < 2:
            return None

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

    def _finalize_chapter(
        self,
        idx: int,
        title: str,
        tagged_narration: str,
        target_seconds: float,
        mood: str,
        visual_intent: str,
        on_screen_date: str,
        scene_type: str,
        dossier: ResearchDossier,
        is_interrupt: bool,
        is_hero_hook: bool,
        quotes: List[Dict[str, str]],
        news_items: List[Dict[str, str]],
    ) -> ScriptChapter:
        """Apply Dual-Layer Speak/Show normalization and visual prompt safety on any chapter."""
        subject = dossier.english_title or dossier.title
        display_clean = normalize_devanagari(strip_inline_tags(tagged_narration))

        if self.language == "hi":
            dual = build_speak_show_alignment_spec(tagged_narration)
            tts_text = dual["tts_tagged_text"]
            speak_words = dual["speak_words"]
            display_spans = dual["display_spans"]
        else:
            tts_text = tagged_narration
            speak_words = [w for w in re.sub(r"[.,?!;:\"'()]+", "", display_clean).split() if w]
            display_spans = [
                {"span_id": f"span_{i+1}", "show": tok, "speak_words": [tok], "speak_start_idx": i, "speak_end_idx": i}
                for i, tok in enumerate(display_clean.split())
                if tok
            ]

        v_type = scene_type
        if is_hero_hook:
            v_type = "hero_ltx_i2v"
        elif v_type not in ("real_photo", "news_card", "quote_card", "map_card", "stat_card", "ai_image", "hero_ltx_i2v"):
            v_type = "real_photo"

        news_headline = ""
        news_source = ""
        if v_type == "news_card" and news_items:
            ni = news_items[idx % len(news_items)]
            news_headline = ni.get("headline", "")
            news_source = ni.get("source", "News Desk")

        quote_speaker = ""
        is_archive_quote = (v_type == "quote_card")
        if is_archive_quote and quotes:
            q = quotes[idx % len(quotes)]
            quote_speaker = q.get("speaker", "Record")

        return ScriptChapter(
            chapter_index=idx + 1,
            title=normalize_devanagari(title),
            narration=display_clean,
            tagged_narration=tagged_narration,
            tts_text=tts_text,
            speak_words=speak_words,
            display_spans=display_spans,
            target_seconds=target_seconds,
            mood=mood if mood in ("mysterious", "curious", "intense", "focused", "inspiring", "epic") else "curious",
            visual_intent=visual_intent,
            layout=self.LAYOUTS[idx % len(self.LAYOUTS)],
            camera=self.CAMERAS[idx % len(self.CAMERAS)],
            on_screen_date=on_screen_date,
            visual_prompt_2d=self._build_visual_prompt(subject, visual_intent, on_screen_date),
            visual_type=v_type,
            is_pattern_interrupt=is_interrupt,
            is_archive_quote=is_archive_quote,
            news_headline=news_headline,
            news_source=news_source,
            quote_speaker=quote_speaker,
        )

    def _build_visual_prompt(self, subject: str, intent: str, date_tag: str) -> str:
        date_note = f", era {date_tag}" if date_tag else ""
        if "2d" in self.style.lower() or "vox" in self.style.lower():
            return f"{_2D_STYLE_PREFIX}, depicting {subject}: {intent}{date_note}, clean editorial composition"
        return f"Subject: {subject}, {intent}{date_note}, {ANTI_VIRTUAL_PROMPT_SUFFIX}"

    def _generate_english_script(
        self, dossier: ResearchDossier, target_duration: int, num_chapters: int, sec_per_ch: float
    ) -> DocumentaryScript:
        facts = dossier.key_facts or [dossier.summary]
        timeline = dossier.timeline or []
        entities = dossier.entities or [dossier.english_title or dossier.title]

        chapter_types = [
            ("The Hook", "mysterious", "Atmospheric wide opening scene with dramatic light contrast"),
            ("How It Started", "curious", "Archival documents, blueprints and early photographic records"),
            ("The Turning Point", "intense", "Dynamic breakthrough moment, crowd and press reaction"),
            ("Inside The System", "focused", "Evidence board, timeline diagram and map trajectory"),
            ("The Hidden Layer", "curious", "Investigative closeup of records and figures"),
            ("The Bigger Picture", "inspiring", "Golden hour editorial cityscape overview"),
            ("What Remains Today", "epic", "Sweeping panoramic closing visual"),
        ]
        conversational_bridges = [
            "Here is where things actually get interesting:",
            "Wait — take a closer look at what happened next:",
            "So why did this change everything? Notice the detail:",
            "Now look at the evidence nobody noticed at first:",
            "Pause for a second and trace that exact timeline:",
            "That single decision set off a massive chain reaction:",
        ]

        chapters: List[ScriptChapter] = []
        subject = dossier.english_title or dossier.title

        for i in range(num_chapters):
            ch_meta = chapter_types[i % len(chapter_types)]
            target_words = max(10, min(28, int(sec_per_ch * self.words_per_sec)))
            date_tag = timeline[i % len(timeline)]["year"] if timeline and (i % 2 == 1) else ""
            entity = entities[i % len(entities)]
            is_interrupt = (i % 3 == 0)

            if i == 0:
                if sec_per_ch <= 7.0:
                    tagged = f"[slow]How did {dossier.title} change our world?[/slow] [pause:0.25s]"
                else:
                    tagged = (
                        f"[slow]Wait — how did {dossier.title} suddenly reshape everything we thought we knew?[/slow] "
                        f"[pause:0.4s] Let's trace what actually happened."
                    )
            elif i == num_chapters - 1:
                if sec_per_ch <= 7.0:
                    tagged = f"And its impact on history still echoes today."
                else:
                    tagged = (
                        f"[slow]Looking back at {dossier.title}, one pattern is crystal clear.[/slow] "
                        f"[pause:0.35s] Every decision still echoes today."
                    )
            else:
                fact_piece = facts[(i - 1) % len(facts)].strip()
                if not fact_piece.endswith((".", "!", "?")):
                    fact_piece += "."
                bridge = conversational_bridges[(i - 1) % len(conversational_bridges)]
                raw = f"{bridge} [pause:0.3s] {fact_piece}" if is_interrupt else fact_piece
                tagged = self._fit_tagged_words(raw, target_words)

            v_intent = f"{ch_meta[2]} featuring {entity}"
            chapters.append(
                self._finalize_chapter(
                    idx=i,
                    title=f"{ch_meta[0]}" if num_chapters <= 7 else f"{ch_meta[0]} ({i + 1})",
                    tagged_narration=tagged,
                    target_seconds=sec_per_ch,
                    mood=ch_meta[1],
                    visual_intent=v_intent,
                    on_screen_date=date_tag,
                    scene_type=("news_card" if (i % 4 == 1 and dossier.news_items) else "real_photo"),
                    dossier=dossier,
                    is_interrupt=is_interrupt,
                    is_hero_hook=(i == 0 or i % 12 == 0),
                    quotes=dossier.verified_quotes,
                    news_items=dossier.news_items,
                )
            )

        return DocumentaryScript(
            topic=dossier.topic,
            english_title=subject,
            language="en",
            style=self.style,
            target_duration=target_duration,
            title=dossier.title,
            hook=chapters[0].narration,
            chapters=chapters,
            conclusion=chapters[-1].narration,
            estimated_duration=sum(ch.target_seconds for ch in chapters),
        )

    def _generate_hindi_script(
        self, dossier: ResearchDossier, target_duration: int, num_chapters: int, sec_per_ch: float
    ) -> DocumentaryScript:
        """Spontaneous conversational Hinglish fallback (no textbook AI clichés)."""
        chapter_types = [
            ("शुरुआत का सवाल", "mysterious", "Atmospheric documentary opening scene with dramatic light"),
            ("असली कहानी कहाँ से शुरू हुई", "curious", "Archival newspaper clipping and historical photograph"),
            ("यहीं पलटी पूरी बाज़ी", "intense", "Press conference and dramatic reaction scene"),
            ("डेटा और सबूतों का खेल", "focused", "Investigative evidence timeline and map chart"),
            ("अंदर की बात", "curious", "Detailed diagram and factual closeup"),
            ("बड़ा खुलासा", "inspiring", "Architectural wide editorial reveal"),
            ("आखिर सीख क्या मिली", "epic", "Panoramic twilight cityscape closing"),
        ]

        hindi_facts = [f for f in dossier.key_facts if contains_devanagari(f)]
        timeline = dossier.timeline or []
        entities = dossier.entities or [dossier.english_title or dossier.title]

        spontaneous_frames = [
            "असल में हुआ ये कि {subject} से जुड़ा ये सच बहुत कम लोगों को पता था।",
            "ज़रा सोचिए — उस वक्त {entity} का एक फैसला पूरी तस्वीर बदलने वाला था।",
            "लेकिन कहानी यहीं खत्म नहीं होती। [pause:0.35s] {entity} के रिकॉर्ड में कुछ और भी था।",
            "अब यहीं पर असली पेंच फँसता है। डेटा साफ़ दिखाता है कि बात कुछ और थी।",
            "ध्यान से देखिए, {subject} का यह हिस्सा सीधे हमारी रोज़मर्रा की ज़िंदगी से जुड़ा है।",
            "आखिर ऐसा हुआ क्यों? इसका जवाब छिपा है पुराने सरकारी और मीडिया रिकॉर्ड में।",
        ]

        chapters: List[ScriptChapter] = []
        subject = dossier.title
        eng_subject = dossier.english_title or dossier.title

        for i in range(num_chapters):
            ch_meta = chapter_types[i % len(chapter_types)]
            target_words = max(12, min(24, int(sec_per_ch * self.words_per_sec)))
            date_tag = timeline[i % len(timeline)]["year"] if timeline and (i % 2 == 1) else ""
            entity = entities[i % len(entities)]
            is_interrupt = (i % 3 == 0)

            if i == 0:
                if sec_per_ch <= 7.0:
                    tagged = f"[fear]ज़रा सोचिए — {subject} की असली कहानी क्या है?[/fear] [pause:0.25s]"
                else:
                    tagged = (
                        f"[fear]ज़रा रुकिए — {subject} की असली कहानी वो नहीं है जो आपने ऊपर-ऊपर से सुनी है।[/fear] "
                        f"[pause:0.45s] आइए इसे बिल्कुल आसान भाषा में समझते हैं।"
                    )
            elif i == num_chapters - 1:
                if sec_per_ch <= 7.0:
                    tagged = f"और यहीं से शुरू होता है असली बदलाव।"
                else:
                    tagged = (
                        f"[slow]तो सीधा निष्कर्ष यही है — {subject} की यह पूरी कहानी हमें बहुत कुछ सोचने पर मजबूर करती है।[/slow] "
                        f"[pause:0.35s] अब फैसला आपका है।"
                    )
            elif hindi_facts and (i - 1) < len(hindi_facts):
                raw_fact = humanize_hindi_rule_based(hindi_facts[i - 1], add_connector=is_interrupt, beat_index=i)
                tagged = f"[slow]{raw_fact}[/slow]" if is_interrupt else raw_fact
            else:
                frame = spontaneous_frames[(i - 1) % len(spontaneous_frames)].format(subject=subject, entity=entity)
                if date_tag:
                    tagged = f"साल {date_tag} में {entity} के आसपास बड़ा बदलाव आया। [pause:0.3s] {frame}"
                else:
                    tagged = frame

            tagged = humanize_hindi_rule_based(self._fit_tagged_words(tagged, target_words), add_connector=False, max_words=target_words)
            v_intent = f"{ch_meta[2]} featuring {entity}"

            chapters.append(
                self._finalize_chapter(
                    idx=i,
                    title=ch_meta[0] if num_chapters <= 7 else f"{ch_meta[0]} ({i + 1})",
                    tagged_narration=tagged,
                    target_seconds=sec_per_ch,
                    mood=ch_meta[1],
                    visual_intent=v_intent,
                    on_screen_date=date_tag,
                    scene_type=("news_card" if (i % 4 == 1 and dossier.news_items) else "real_photo"),
                    dossier=dossier,
                    is_interrupt=is_interrupt,
                    is_hero_hook=(i == 0 or i % 12 == 0),
                    quotes=dossier.verified_quotes,
                    news_items=dossier.news_items,
                )
            )

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
        plain = strip_inline_tags(text)
        words = plain.split()
        if len(words) > target_words + 6:
            trimmed = " ".join(words[:target_words + 2])
            last_punct = max(trimmed.rfind("."), trimmed.rfind(","), trimmed.rfind("।"), trimmed.rfind("?"))
            if last_punct > 15:
                return trimmed[:last_punct + 1]
            ending = "।" if contains_devanagari(trimmed) else "."
            return trimmed + ending
        return text

    def _fit_tagged_words(self, tagged_text: str, target_words: int) -> str:
        plain_words = strip_inline_tags(tagged_text).split()
        if len(plain_words) <= target_words + 6:
            return tagged_text
        # Trim neatly inside tag wrappers if plain word count overflows budget
        trimmed_plain = self._fit_narration_words(strip_inline_tags(tagged_text), target_words)
        m = re.match(r"^\[(slow|fear|angry|fast)\](.*)\[/\1\]$", tagged_text.strip(), flags=re.IGNORECASE | re.DOTALL)
        if m:
            return f"[{m.group(1).lower()}]{trimmed_plain}[/{m.group(1).lower()}]"
        return trimmed_plain
