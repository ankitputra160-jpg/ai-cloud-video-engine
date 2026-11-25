"""
engine/storyboard.py - Stage C: Dynamic Storyboard Planning & Scene Schema
Creates structured scene-by-scene blueprints with precise visual, auditory, and timing cues.
"""
import json
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
    
    # Asset tracking populated during stages D & E
    video_asset_path: Optional[str] = None
    voice_asset_path: Optional[str] = None
    sfx_asset_path: Optional[str] = None
    asset_source: Optional[str] = None

@dataclass
class StoryboardManifest:
    topic: str
    language: str
    target_duration: int
    scenes: List[SceneDefinition] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.scenes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "language": self.language,
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
        topic_clean = script.topic.lower()

        for idx, chapter in enumerate(script.chapters):
            scene_num = idx + 1
            scene_id = f"scene_{scene_num:02d}"

            # Formulate dynamic visual description and search queries
            queries = self._generate_search_queries(topic_clean, chapter)
            ai_prompt = (
                f"Cinematic documentary footage of {script.title}, {chapter.visual_intent}. "
                f"Hyper-realistic, 8k resolution, 35mm film aesthetic, professional color grading."
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
                subtitle_text=chapter.narration
            ))

        return StoryboardManifest(
            topic=script.topic,
            language=script.language,
            target_duration=script.target_duration,
            scenes=scenes
        )

    def _generate_search_queries(self, topic: str, chapter: ScriptChapter) -> List[str]:
        """Derive 3-4 distinct search queries combining subject and visual mood."""
        # Clean words from title
        key_words = [w for w in topic.split() if len(w) > 3][:3]
        base_subject = " ".join(key_words) or topic

        queries = [
            f"{base_subject} {chapter.mood}",
            f"{base_subject} cinematic",
            f"{base_subject} workshop craftsmanship" if "restoration" in topic or "craft" in topic else f"{base_subject} history archive",
            f"{base_subject} 4k"
        ]
        return queries
