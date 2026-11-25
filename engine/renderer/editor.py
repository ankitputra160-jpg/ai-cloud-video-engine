"""
engine/renderer/editor.py - Master Video Editing & Timeline Assembly
Assembles multi-scene video tracks, applies transitions, burns subtitles, and outputs faststart MP4.
"""
import os
import subprocess
import logging
import tempfile
from typing import List, Optional
from engine.config import PipelineConfig
from engine.storyboard import StoryboardManifest, SceneDefinition
from engine.renderer.ffmpeg_utils import safe_run_ffmpeg, get_duration

logger = logging.getLogger("renderer.editor")

class VideoEditor:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.rendered_dir = os.path.join(config.work_dir, "rendered_scenes")
        os.makedirs(self.rendered_dir, exist_ok=True)

    def assemble_documentary(self, manifest: StoryboardManifest, srt_path: Optional[str] = None) -> Optional[str]:
        """Assemble all storyboard scenes, mux audio tracks, burn subtitles, and generate final MP4."""
        logger.info(f"Assembling documentary: {len(manifest.scenes)} scenes...")
        assembled_scenes: List[str] = []

        # 1. Combine normalized video + mixed audio for each scene
        for scene in manifest.scenes:
            scene_mp4 = os.path.join(self.rendered_dir, f"assembled_{scene.scene_id}.mp4")
            if not scene.video_asset_path or not os.path.exists(scene.video_asset_path):
                logger.error(f"Missing video asset for {scene.scene_id}")
                return None

            success = self._mux_video_and_audio(
                scene.video_asset_path,
                scene.voice_asset_path,
                scene_mp4,
                scene.duration
            )
            if success and os.path.exists(scene_mp4):
                assembled_scenes.append(scene_mp4)
            else:
                logger.error(f"Failed to assemble scene {scene.scene_id}")
                return None

        # 2. Concatenate all assembled scenes
        temp_raw_concat = os.path.join(self.config.work_dir, "raw_concatenated.mp4")
        concat_success = self._concat_scenes(assembled_scenes, temp_raw_concat)
        if not concat_success or not os.path.exists(temp_raw_concat):
            logger.error("Failed to concatenate scenes")
            return None

        # 3. Apply subtitles (if requested) and fast-start MP4 packaging
        final_output = self.config.output_path
        os.makedirs(os.path.dirname(final_output), exist_ok=True)

        if self.config.burn_subtitles and srt_path and os.path.exists(srt_path):
            logger.info("Burning subtitles into final documentary stream...")
            self._burn_subtitles_and_package(temp_raw_concat, srt_path, final_output)
        else:
            logger.info("Packaging final fast-start MP4...")
            self._package_faststart(temp_raw_concat, final_output)

        if os.path.exists(final_output) and os.path.getsize(final_output) > 10000:
            logger.info(f"🎉 Final documentary ready: {final_output} ({os.path.getsize(final_output)//1024} KB)")
            return final_output

        return None

    def _mux_video_and_audio(self, video_path: str, audio_path: Optional[str], output_path: str, duration: float) -> bool:
        prof = self.config.profile
        if audio_path and os.path.exists(audio_path):
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                output_path
            ]
        else:
            # Generate silent audio stream if no audio file present
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-t", str(duration),
                output_path
            ]
        return safe_run_ffmpeg(cmd, f"Muxing {os.path.basename(output_path)}")

    def _concat_scenes(self, scene_files: List[str], output_path: str) -> bool:
        concat_txt = os.path.join(self.config.work_dir, "concat_manifest.txt")
        with open(concat_txt, "w", encoding="utf-8") as f:
            for s in scene_files:
                # Absolute path with safe escaping
                abs_p = os.path.abspath(s).replace("'", "'\\''")
                f.write(f"file '{abs_p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", str(self.config.profile.crf),
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]
        return safe_run_ffmpeg(cmd, "Concatenating scenes")

    def _burn_subtitles_and_package(self, input_video: str, srt_path: str, output_path: str) -> bool:
        """Burn subtitles with clean documentary typography (yellow/white text, subtle dark outline)."""
        # Escape path for FFmpeg subtitles filter
        escaped_srt = os.path.abspath(srt_path).replace("\\", "/").replace(":", "\\:")
        subtitle_filter = (
            f"subtitles='{escaped_srt}':force_style="
            f"'FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=3,Outline=1.5,Shadow=1,Alignment=2,MarginV=30'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(self.config.profile.crf),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path
        ]
        success = safe_run_ffmpeg(cmd, "Burning subtitles", timeout=600)
        if not success:
            logger.warning("Subtitles filter failed (font or libass issue), fallback to packaging without burned subtitles")
            return self._package_faststart(input_video, output_path)
        return True

    def _package_faststart(self, input_video: str, output_path: str) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path
        ]
        return safe_run_ffmpeg(cmd, "Packaging faststart MP4")
