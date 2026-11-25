"""
engine/voice/subtitles.py - Subtitle Generator & Timing Synchronizer
Generates standard SRT and ASS subtitle files aligned with documentary narration.
"""
import os
from typing import List
from engine.storyboard import StoryboardManifest

class SubtitleGenerator:
    @staticmethod
    def format_timestamp_srt(seconds: float) -> str:
        """Format seconds into SRT timestamp HH:MM:SS,mmm"""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    @classmethod
    def generate_srt(cls, manifest: StoryboardManifest, output_path: str) -> str:
        """Create a standard SubRip (.srt) subtitle file from the storyboard manifest."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        current_time = 0.0
        srt_entries: List[str] = []

        for idx, scene in enumerate(manifest.scenes):
            start_time = current_time + 0.3  # Slight lead-in
            end_time = current_time + max(1.0, scene.duration - 0.3)  # Slight lead-out
            
            # Wrap long text cleanly
            clean_text = scene.subtitle_text.strip()
            
            srt_entry = (
                f"{idx + 1}\n"
                f"{cls.format_timestamp_srt(start_time)} --> {cls.format_timestamp_srt(end_time)}\n"
                f"{clean_text}\n"
            )
            srt_entries.append(srt_entry)
            current_time += scene.duration

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_entries))

        return output_path
