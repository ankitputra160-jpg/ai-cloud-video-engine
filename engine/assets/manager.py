"""
engine/assets/manager.py - Visual Asset Manager & Fallback Orchestrator
Coordinates multi-tier visual search and normalizes video streams to standard resolution and frame rate.
"""
import os
import subprocess
import logging
from typing import List, Optional
from engine.config import PipelineConfig
from engine.storyboard import StoryboardManifest, SceneDefinition
from engine.assets.base import VisualAssetProvider
from engine.assets.pexels import PexelsProvider
from engine.assets.pixabay import PixabayProvider
from engine.assets.wikimedia import WikimediaCommonsProvider
from engine.assets.ai_visuals import CinematicMotionVisualProvider

logger = logging.getLogger("assets.manager")

class VisualAssetManager:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.providers: List[VisualAssetProvider] = [
            PexelsProvider(api_key=config.pexels_api_key, timeout=config.http_timeout),
            PixabayProvider(api_key=config.pixabay_api_key, timeout=config.http_timeout),
            WikimediaCommonsProvider(timeout=config.http_timeout),
            CinematicMotionVisualProvider(
                width=config.profile.width,
                height=config.profile.height,
                fps=config.profile.fps
            )
        ]
        self.assets_dir = os.path.join(config.work_dir, "visual_assets")
        os.makedirs(self.assets_dir, exist_ok=True)

    def retrieve_assets_for_storyboard(self, manifest: StoryboardManifest) -> StoryboardManifest:
        """Process each scene in manifest, retrieve or synthesize visual footage, and normalize."""
        logger.info(f"Retrieving visual assets for {len(manifest.scenes)} scenes...")

        for idx, scene in enumerate(manifest.scenes):
            raw_path = os.path.join(self.assets_dir, f"raw_{scene.scene_id}.mp4")
            normalized_path = os.path.join(self.assets_dir, f"norm_{scene.scene_id}.mp4")

            found_path = None
            source_used = None

            # Attempt providers in priority order
            for provider in self.providers:
                if provider.is_available():
                    logger.info(f"[{scene.scene_id}] Trying provider: {provider.name}")
                    result = provider.fetch_video(scene.footage_queries, raw_path, min_duration=scene.duration)
                    if result and os.path.exists(result) and os.path.getsize(result) > 1000:
                        found_path = result
                        source_used = provider.name
                        break

            # Guarantee fallback if no provider succeeded
            if not found_path:
                logger.info(f"[{scene.scene_id}] Generating cinematic motion backdrop...")
                motion_gen = CinematicMotionVisualProvider(
                    width=self.config.profile.width,
                    height=self.config.profile.height,
                    fps=self.config.profile.fps
                )
                found_path = motion_gen.generate_motion_clip(
                    raw_path,
                    title=scene.title,
                    duration=scene.duration,
                    mood=scene.bgm_mood
                )
                source_used = "cinematic_motion_generator"

            # Normalize video stream to exact specs (resolution, 25fps, duration, strip audio)
            self._normalize_clip(found_path, normalized_path, scene.duration)

            scene.video_asset_path = normalized_path
            scene.asset_source = source_used

        return manifest

    def _normalize_clip(self, input_path: str, output_path: str, target_duration: float):
        """Converts any video to specified 1080p/4k standard, 25fps, fixed duration, stripping native audio."""
        prof = self.config.profile
        vf = (
            f"scale={prof.width}:{prof.height}:force_original_aspect_ratio=decrease,"
            f"pad={prof.width}:{prof.height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={prof.fps},setsar=1"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf,
            "-t", str(target_duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", str(prof.crf),
            "-an",
            output_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg normalization failed for {input_path}: {res.stderr[-300:]}")
            # In case of error, produce a clean emergency fallback clip
            emergency_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=#101827:s={prof.width}x{prof.height}:r={prof.fps}:d={target_duration}",
                "-t", str(target_duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                output_path
            ]
            subprocess.run(emergency_cmd, capture_output=True)
