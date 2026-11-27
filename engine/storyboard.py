"""
engine/storyboard.py - Module 2: HookAndBeatArchitect & Multi-Cut Storyboard Schema
Splits audio-stable 12-16s scenes into 3-5s fast-cut visual micro-beats following the
45% Real Photos : 25% Playwright Motion Cards : 25% FLUX AI Images : 5% Hero LTX I2V ratio.
Preserves full JSON backward compatibility with earlier storyboards.
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from engine.scriptwriter import (
    ANTI_VIRTUAL_NEGATIVE_PROMPT,
    ANTI_VIRTUAL_PROMPT_SUFFIX,
    DocumentaryScript,
    ScriptChapter,
)


@dataclass
class SceneDefinition:
    scene_id: str
    chapter_index: int
    title: str
    narration: str
    visual_description: str
    footage_queries: List[str]
    ai_prompt: str
    duration: float
    transition: str
    bgm_mood: str
    sfx_tag: str
    subtitle_text: str

    # 2D & Motion Direction metadata
    layout: str = "hero"
    camera: str = "push_in"
    on_screen_date: str = ""
    preferred_media_url: Optional[str] = None

    # v3.0 Expressive Prosody, Speak/Show Sync & 3-5s Sub-Beats
    tagged_narration: str = ""
    tts_text: str = ""
    speak_words: List[str] = field(default_factory=list)
    display_spans: List[Dict[str, Any]] = field(default_factory=list)
    visual_type: str = "real_photo"
    negative_prompt: str = ANTI_VIRTUAL_NEGATIVE_PROMPT
    is_pattern_interrupt: bool = False
    is_archive_quote: bool = False
    news_headline: str = ""
    news_source: str = ""
    quote_speaker: str = ""
    visual_beats: List[Dict[str, Any]] = field(default_factory=list)

    # Asset & Word-Timing tracking populated during Audio-First & Visual stages
    video_asset_path: Optional[str] = None
    voice_asset_path: Optional[str] = None
    sfx_asset_path: Optional[str] = None
    asset_source: Optional[str] = None
    word_timings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StoryboardManifest:
    topic: str
    language: str
    target_duration: int
    scenes: List[SceneDefinition] = field(default_factory=list)
    style: str = "Documentary"

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.scenes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "language": self.language,
            "style": self.style,
            "target_duration": self.target_duration,
            "total_duration": self.total_duration,
            "scene_count": len(self.scenes),
            "scenes": [asdict(s) for s in self.scenes],
        }

    def save_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, filepath: str) -> "StoryboardManifest":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid_fields = SceneDefinition.__dataclass_fields__.keys()
        scenes = [
            SceneDefinition(**{k: v for k, v in s.items() if k in valid_fields})
            for s in data["scenes"]
        ]
        return cls(
            topic=data["topic"],
            language=data["language"],
            target_duration=data["target_duration"],
            style=data.get("style", "Documentary"),
            scenes=scenes,
        )


class StoryboardEngine:
    """HookAndBeatArchitect: plans 3-5s hybrid visual beats inside stable 12-16s scenes."""

    TRANSITIONS = ["fade", "dissolve", "crossfade", "wipeleft", "slideup"]
    SFX_POOL = {
        "mysterious": "deep_sub_hit",
        "curious": "soft_whoosh",
        "intense": "deep_sub_hit",
        "focused": "subtle_pop",
        "inspiring": "soft_whoosh",
        "epic": "deep_sub_hit",
    }

    # Strict 45 : 25 : 25 : 5 cadence pattern across every 20 beats
    HYBRID_BEAT_CYCLE = (
        "hero_ltx_i2v",   # 1 (5% hero)
        "real_photo",     # 2
        "news_card",      # 3
        "ai_image",       # 4
        "real_photo",     # 5
        "map_card",       # 6
        "real_photo",     # 7
        "ai_image",       # 8
        "stat_card",      # 9
        "real_photo",     # 10
        "real_photo",     # 11
        "ai_image",       # 12
        "news_card",      # 13
        "real_photo",     # 14
        "ai_image",       # 15
        "real_photo",     # 16
        "quote_card",     # 17
        "real_photo",     # 18
        "ai_image",       # 19
        "real_photo",     # 20
    )

    def generate_storyboard(self, script: DocumentaryScript) -> StoryboardManifest:
        """Transform narrative chapters into executable multi-beat documentary scenes."""
        scenes: List[SceneDefinition] = []
        base_subject = (script.english_title or script.topic).strip()
        pad_width = 3 if len(script.chapters) >= 100 else 2
        beat_counter = 0

        for idx, chapter in enumerate(script.chapters):
            scene_num = idx + 1
            scene_id = f"scene_{scene_num:0{pad_width}d}"

            queries = self._generate_search_queries(base_subject, chapter, idx)
            ai_prompt = chapter.visual_prompt_2d or (
                f"Cinematic documentary visual of {base_subject}, {chapter.visual_intent}, {ANTI_VIRTUAL_PROMPT_SUFFIX}"
            )

            transition = self.TRANSITIONS[idx % len(self.TRANSITIONS)]
            sfx = self._sfx_for_visual(chapter.visual_type, chapter.mood, is_hook=(idx == 0))

            # Build 2-4 sub-beats of ~3.5-5.0s inside each audio chapter for Dhruv Rathee pacing
            n_sub = max(1, min(4, int(round(max(3.5, chapter.target_seconds) / 4.2))))
            sub_dur = round(chapter.target_seconds / n_sub, 3)
            sub_beats: List[Dict[str, Any]] = []
            for b in range(n_sub):
                cycle_type = self.HYBRID_BEAT_CYCLE[beat_counter % len(self.HYBRID_BEAT_CYCLE)]
                if idx == 0 and b == 0:
                    cycle_type = "hero_ltx_i2v"
                elif b == 0 and chapter.visual_type != "real_photo":
                    cycle_type = chapter.visual_type

                beat_sfx = self._sfx_for_visual(cycle_type, chapter.mood, is_hook=(idx == 0 and b == 0))
                sub_beats.append({
                    "beat_id": f"{scene_id}_b{b + 1}",
                    "visual_type": cycle_type,
                    "duration": sub_dur,
                    "camera": ("push_in" if b % 2 == 0 else "pan_right"),
                    "query": queries[b % len(queries)],
                    "ai_prompt": f"{ai_prompt}, dynamic angle variation {b + 1}",
                    "sfx_tag": beat_sfx,
                    "headline": chapter.news_headline or chapter.title,
                    "source": chapter.news_source or "Archival Desk",
                    "quote_speaker": chapter.quote_speaker,
                    "date_badge": chapter.on_screen_date,
                    "asset_path": None,
                })
                beat_counter += 1

            scenes.append(SceneDefinition(
                scene_id=scene_id,
                chapter_index=chapter.chapter_index,
                title=chapter.title,
                narration=chapter.narration,
                visual_description=chapter.visual_intent,
                footage_queries=queries,
                ai_prompt=ai_prompt,
                duration=round(chapter.target_seconds, 3),
                transition=transition,
                bgm_mood=chapter.mood,
                sfx_tag=sfx,
                subtitle_text=chapter.narration,
                layout=chapter.layout,
                camera=chapter.camera,
                on_screen_date=chapter.on_screen_date,
                tagged_narration=chapter.tagged_narration or chapter.narration,
                tts_text=chapter.tts_text or chapter.narration,
                speak_words=list(chapter.speak_words),
                display_spans=list(chapter.display_spans),
                visual_type=chapter.visual_type,
                negative_prompt=ANTI_VIRTUAL_NEGATIVE_PROMPT,
                is_pattern_interrupt=chapter.is_pattern_interrupt,
                is_archive_quote=chapter.is_archive_quote,
                news_headline=chapter.news_headline,
                news_source=chapter.news_source,
                quote_speaker=chapter.quote_speaker,
                visual_beats=sub_beats,
            ))

        return StoryboardManifest(
            topic=script.topic,
            language=script.language,
            target_duration=script.target_duration,
            style=script.style,
            scenes=scenes,
        )

    @classmethod
    def _sfx_for_visual(cls, visual_type: str, mood: str, is_hook: bool = False) -> str:
        if is_hook or visual_type == "hero_ltx_i2v":
            return "deep_sub_hit"
        if visual_type == "news_card":
            return "paper_rustle"
        if visual_type in ("stat_card", "map_card"):
            return "subtle_pop"
        if visual_type == "quote_card":
            return "camera_click"
        return cls.SFX_POOL.get(mood, "soft_whoosh")

    def _generate_search_queries(self, subject: str, chapter: ScriptChapter, idx: int = 0) -> List[str]:
        """Derive distinct, topic-grounded visual search queries for each scene."""
        stop = {"the", "secrets", "history", "story", "mystery", "and", "for", "with", "from"}
        tokens = [w for w in re.findall(r"[A-Za-z0-9]+", subject) if w.lower() not in stop and len(w) > 2]
        core = " ".join(tokens[:4]) or subject

        entity_match = re.search(r"featuring\s+(.+)$", chapter.visual_intent, re.IGNORECASE)
        entity = entity_match.group(1).strip() if entity_match else ""

        modifiers = [
            "press photograph archive",
            "documentary scene landscape",
            "government official building",
            "crowd public demonstration",
            "editorial news photo",
            "vintage historical diagram",
        ]
        mod = modifiers[idx % len(modifiers)]

        queries = []
        if entity and entity.lower() not in core.lower() and re.match(r"^[A-Za-z0-9\s\-]+$", entity):
            queries.append(f"{entity} {core}")
            queries.append(entity)
        queries.append(f"{core} {mod}")
        queries.append(core)
        return queries
