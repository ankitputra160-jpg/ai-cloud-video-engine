"""
engine/storyboard.py - Stage C: Dynamic Storyboard Planning & Scene Schema
Creates structured scene-by-scene blueprints with 2D layout, camera, visual, auditory, and timing cues.
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from engine.scriptwriter import DocumentaryScript, ScriptChapter

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

    # Asset & Word-Timing tracking populated during stages D & E
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
            "scenes": [asdict(s) for s in self.scenes]
        }

    def save_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, filepath: str) -> "StoryboardManifest":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        scenes = [SceneDefinition(**s) for s in data["scenes"]]
        return cls(
            topic=data["topic"],
            language=data["language"],
            target_duration=data["target_duration"],
            style=data.get("style", "Documentary"),
            scenes=scenes
        )


class StoryboardEngine:
    TRANSITIONS = ["fade", "dissolve", "crossfade", "wipeleft", "slideup"]
    SFX_POOL = {
        "mysterious": "ambient_wind",
        "curious": "subtle_clicks",
        "intense": "mechanical_grinder",
        "focused": "precision_tool",
        "inspiring": "reveal_chime",
        "epic": "low_bass_rumble"
    }

    def generate_storyboard(self, script: DocumentaryScript) -> StoryboardManifest:
        """Transform narrative chapters into a concrete, executable multi-scene storyboard."""
        scenes: List[SceneDefinition] = []
        base_subject = (script.english_title or script.topic).strip()
        pad_width = 3 if len(script.chapters) >= 100 else 2

        for idx, chapter in enumerate(script.chapters):
            scene_num = idx + 1
            scene_id = f"scene_{scene_num:0{pad_width}d}"

            queries = self._generate_search_queries(base_subject, chapter, idx)
            ai_prompt = chapter.visual_prompt_2d or (
                f"Cinematic documentary visual of {base_subject}, {chapter.visual_intent}. "
                f"High detail, clean editorial composition, balanced atmospheric lighting."
            )

            transition = self.TRANSITIONS[idx % len(self.TRANSITIONS)]
            sfx = self.SFX_POOL.get(chapter.mood, "ambient_wind")

            scenes.append(SceneDefinition(
                scene_id=scene_id,
                chapter_index=chapter.chapter_index,
                title=chapter.title,
                narration=chapter.narration,
                visual_description=chapter.visual_intent,
                footage_queries=queries,
                ai_prompt=ai_prompt,
                duration=round(chapter.target_seconds, 2),
                transition=transition,
                bgm_mood=chapter.mood,
                sfx_tag=sfx,
                subtitle_text=chapter.narration,
                layout=chapter.layout,
                camera=chapter.camera,
                on_screen_date=chapter.on_screen_date,
            ))

        return StoryboardManifest(
            topic=script.topic,
            language=script.language,
            target_duration=script.target_duration,
            style=script.style,
            scenes=scenes
        )

    def _generate_search_queries(self, subject: str, chapter: ScriptChapter, idx: int = 0) -> List[str]:
        """Derive distinct, topic-grounded visual search queries for each scene."""
        stop = {"the", "secrets", "history", "story", "mystery", "and", "for", "with", "from"}
        tokens = [w for w in re.findall(r"[A-Za-z0-9]+", subject) if w.lower() not in stop and len(w) > 2]
        core = " ".join(tokens[:4]) or subject

        # Extract any specific entity mentioned in visual_intent ("featuring X")
        entity_match = re.search(r"featuring\s+(.+)$", chapter.visual_intent, re.IGNORECASE)
        entity = entity_match.group(1).strip() if entity_match else ""

        modifiers = [
            "historical illustration",
            "observatory architecture landscape",
            "ancient manuscript science",
            "cinematic documentary",
            "monument aerial",
            "vintage diagram",
        ]
        mod = modifiers[idx % len(modifiers)]

        queries = []
        if entity and entity.lower() not in core.lower() and re.match(r"^[A-Za-z0-9\s\-]+$", entity):
            queries.append(f"{entity} {core}")
            queries.append(entity)
        queries.append(f"{core} {mod}")
        queries.append(core)
        return queries
