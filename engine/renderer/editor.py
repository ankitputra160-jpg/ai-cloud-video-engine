"""
engine/renderer/editor.py - Stage G: Scalable Parallel Video Assembly & Devanagari Subtitle Engine
Burns HarfBuzz-shaped ASS subtitles (pointing to bundled Noto Devanagari fonts) and muxes audio
in a single pass per scene in parallel, then concatenates with stream copy (-c copy) and +faststart.
Scales effortlessly from 10-second clips up to 25-minute (1500s) documentaries.
"""
import concurrent.futures
import logging
import os
from typing import List, Optional

from engine.config import PipelineConfig
from engine.renderer.ffmpeg_utils import safe_run_ffmpeg
from engine.storyboard import SceneDefinition, StoryboardManifest
from engine.text.devanagari import get_fonts_dir
from engine.voice.subtitles import SubtitleGenerator

logger = logging.getLogger("renderer.editor")


def _escape_ffmpeg_filter_path(path: str) -> str:
    """Escape file or directory paths safely for FFmpeg subtitles/ass filter expressions."""
    return os.path.abspath(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


class VideoEditor:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.rendered_dir = os.path.join(config.work_dir, "rendered_scenes")
        self.sub_dir = os.path.join(config.work_dir, "scene_subs")
        os.makedirs(self.rendered_dir, exist_ok=True)
        os.makedirs(self.sub_dir, exist_ok=True)

    def _process_single_scene(self, scene: SceneDefinition) -> Optional[str]:
        """Mux audio and burn scene-level ASS subtitles in a single FFmpeg pass."""
        scene_mp4 = os.path.join(self.rendered_dir, f"assembled_{scene.scene_id}.mp4")
        if not scene.video_asset_path or not os.path.exists(scene.video_asset_path):
            logger.error(f"Missing video asset for {scene.scene_id}")
            return None

        prof = self.config.profile
        ass_path: Optional[str] = None
        if self.config.burn_subtitles and self.config.subtitle_style != "srt_classic":
            ass_path = os.path.join(self.sub_dir, f"{scene.scene_id}.ass")
            SubtitleGenerator.generate_scene_ass(
                scene,
                ass_path,
                language=self.config.language,
                width=prof.width,
                height=prof.height,
                style_mode=self.config.subtitle_style,
            )

        success = self._render_scene_pass(
            video_path=scene.video_asset_path,
            audio_path=scene.voice_asset_path,
            output_path=scene_mp4,
            duration=scene.duration,
            ass_path=ass_path,
        )

        # Fallback without subtitle filter if libass unavailable on host FFmpeg
        if not success and ass_path:
            logger.warning(f"[{scene.scene_id}] Retrying scene mux without ASS filter...")
            success = self._render_scene_pass(
                video_path=scene.video_asset_path,
                audio_path=scene.voice_asset_path,
                output_path=scene_mp4,
                duration=scene.duration,
                ass_path=None,
            )

        if success and os.path.exists(scene_mp4):
            return scene_mp4
        return None

    def assemble_documentary(self, manifest: StoryboardManifest, srt_path: Optional[str] = None) -> Optional[str]:
        """Assemble scenes in parallel, concatenate via stream copy, and package fast-start MP4."""
        logger.info(f"Assembling documentary: {len(manifest.scenes)} scenes...")
        max_workers = min(4, max(1, (os.cpu_count() or 2)))

        assembled_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_idx = {
                pool.submit(self._process_single_scene, scene): idx
                for idx, scene in enumerate(manifest.scenes)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                res_path = future.result()
                if not res_path:
                    logger.error(f"Failed to assemble scene index {idx}")
                    return None
                assembled_map[idx] = res_path

        assembled_scenes = [assembled_map[i] for i in range(len(manifest.scenes))]

        final_output = self.config.output_path
        os.makedirs(os.path.dirname(final_output) or ".", exist_ok=True)

        # If caller explicitly requested srt_classic, concatenate and burn SRT at end
        if self.config.burn_subtitles and self.config.subtitle_style == "srt_classic" and srt_path and os.path.exists(srt_path):
            temp_concat = os.path.join(self.config.work_dir, "raw_concatenated.mp4")
            if not self._concat_scenes_copy(assembled_scenes, temp_concat):
                return None
            self._burn_srt_and_package(temp_concat, srt_path, final_output)
        else:
            # Scenes already contain ASS subtitles; zero-reencode stream copy concat -> <5s even for 25 min!
            if not self._concat_scenes_copy(assembled_scenes, final_output, faststart=True):
                return None

        if os.path.exists(final_output) and os.path.getsize(final_output) > 10000:
            logger.info(f"🎉 Final documentary ready: {final_output} ({os.path.getsize(final_output)//1024} KB)")
            return final_output

        return None

    def _render_scene_pass(
        self,
        video_path: str,
        audio_path: Optional[str],
        output_path: str,
        duration: float,
        ass_path: Optional[str] = None,
    ) -> bool:
        prof = self.config.profile
        cmd = ["ffmpeg", "-y", "-i", video_path]

        if audio_path and os.path.exists(audio_path):
            cmd.extend(["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0"])
        else:
            cmd.extend([
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-map", "0:v:0", "-map", "1:a:0",
            ])

        if ass_path and os.path.exists(ass_path):
            esc_ass = _escape_ffmpeg_filter_path(ass_path)
            fonts_dir = get_fonts_dir()
            if os.path.isdir(fonts_dir):
                esc_fonts = _escape_ffmpeg_filter_path(fonts_dir)
                vf_str = f"ass='{esc_ass}':fontsdir='{esc_fonts}'"
            else:
                vf_str = f"ass='{esc_ass}'"
            cmd.extend(["-vf", vf_str, "-c:v", "libx264", "-preset", "fast", "-crf", str(prof.crf), "-pix_fmt", "yuv420p"])
        else:
            cmd.extend(["-c:v", "copy"])

        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-t", str(duration), output_path])
        return safe_run_ffmpeg(cmd, f"Scene render {os.path.basename(output_path)}", timeout=180)

    def _concat_scenes_copy(self, scene_files: List[str], output_path: str, faststart: bool = False) -> bool:
        concat_txt = os.path.join(self.config.work_dir, "concat_manifest.txt")
        with open(concat_txt, "w", encoding="utf-8") as f:
            for s in scene_files:
                abs_p = os.path.abspath(s).replace("'", "'\\''")
                f.write(f"file '{abs_p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt,
            "-c", "copy",
        ]
        if faststart:
            cmd.extend(["-movflags", "+faststart"])
        cmd.append(output_path)

        ok = safe_run_ffmpeg(cmd, "Concatenating scenes (stream copy)", timeout=300)
        if ok:
            return True

        # Safe fallback re-encode if stream params differed across clips
        cmd_reenc = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_txt,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(self.config.profile.crf),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        return safe_run_ffmpeg(cmd_reenc, "Concatenating scenes (fallback re-encode)", timeout=900)

    def _burn_srt_and_package(self, input_video: str, srt_path: str, output_path: str) -> bool:
        escaped_srt = _escape_ffmpeg_filter_path(srt_path)
        font_name = "Noto Sans Devanagari" if self.config.language == "hi" else "Arial"
        fonts_dir = get_fonts_dir()
        fonts_opt = f":fontsdir='{_escape_ffmpeg_filter_path(fonts_dir)}'" if os.path.isdir(fonts_dir) else ""

        subtitle_filter = (
            f"subtitles='{escaped_srt}'{fonts_opt}:force_style="
            f"'FontName={font_name},FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=4,BackColour=&HCC0F172A,Outline=1.5,Shadow=0,Alignment=2,MarginV=36'"
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
            output_path,
        ]
        success = safe_run_ffmpeg(cmd, "Burning SRT subtitles", timeout=900)
        if not success:
            return self._package_faststart(input_video, output_path)
        return True

    def _package_faststart(self, input_video: str, output_path: str) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        return safe_run_ffmpeg(cmd, "Packaging faststart MP4")
