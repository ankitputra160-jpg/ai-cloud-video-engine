"""
engine/assets/manager.py - Visual Asset Manager & Multi-Provider Cascade Orchestrator
Coordinates stock video, NASA archive, Wikimedia Commons (video & high-res photos),
keyless Pollinations 2D AI illustrations, and 2D motion cards with duplicate-asset protection.
"""
import logging
import os
import subprocess
from typing import List, Optional, Set

from engine.assets.ai_visuals import CinematicMotionVisualProvider
from engine.assets.base import VisualAssetProvider
from engine.assets.nasa import NasaMediaProvider
from engine.assets.pexels import PexelsProvider
from engine.assets.pixabay import PixabayProvider
from engine.assets.pollinations import PollinationsAIProvider
from engine.assets.wikimedia import WikimediaCommonsProvider
from engine.config import PipelineConfig
from engine.storyboard import StoryboardManifest

logger = logging.getLogger("assets.manager")


class VisualAssetManager:
    def __init__(self, config: PipelineConfig):
        self.config = config
        w, h, fps = config.profile.width, config.profile.height, config.profile.fps

        self.pexels = PexelsProvider(api_key=config.pexels_api_key, timeout=config.http_timeout)
        self.pixabay = PixabayProvider(api_key=config.pixabay_api_key, timeout=config.http_timeout)
        self.nasa = NasaMediaProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.wikimedia = WikimediaCommonsProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.pollinations = PollinationsAIProvider(timeout=max(20, config.http_timeout), width=w, height=h, fps=fps)
        self.motion_gen = CinematicMotionVisualProvider(width=w, height=h, fps=fps)

        if config.is_2d_style:
            self.providers: List[VisualAssetProvider] = [
                self.pollinations,
                self.wikimedia,
                self.nasa,
                self.pexels,
                self.pixabay,
                self.motion_gen,
            ]
        else:
            self.providers = [
                self.pexels,
                self.pixabay,
                self.nasa,
                self.wikimedia,
                self.pollinations,
                self.motion_gen,
            ]

        self.assets_dir = os.path.join(config.work_dir, "visual_assets")
        os.makedirs(self.assets_dir, exist_ok=True)

    def retrieve_assets_for_storyboard(self, manifest: StoryboardManifest) -> StoryboardManifest:
        """Retrieve or synthesize unique visual footage per scene and normalize to exact stream specs."""
        logger.info(f"Retrieving visual assets for {len(manifest.scenes)} scenes (2D Mode: {self.config.is_2d_style})...")
        used_urls: Set[str] = set()

        for idx, scene in enumerate(manifest.scenes):
            raw_path = os.path.join(self.assets_dir, f"raw_{scene.scene_id}.mp4")
            normalized_path = os.path.join(self.assets_dir, f"norm_{scene.scene_id}.mp4")

            found_path = None
            source_used = None

            for provider in self.providers:
                if not provider.is_available():
                    continue
                if isinstance(provider, NasaMediaProvider) and not provider.is_topic_relevant(scene.footage_queries):
                    continue

                logger.info(f"[{scene.scene_id}] Trying provider: {provider.name}")
                if isinstance(provider, WikimediaCommonsProvider):
                    result = provider.fetch_video(
                        scene.footage_queries,
                        raw_path,
                        min_duration=scene.duration,
                        used_urls=used_urls,
                        camera=scene.camera,
                        date_badge=scene.on_screen_date,
                        prefer_images=self.config.is_2d_style,
                    )
                elif isinstance(provider, NasaMediaProvider):
                    result = provider.fetch_video(
                        scene.footage_queries,
                        raw_path,
                        min_duration=scene.duration,
                        used_urls=used_urls,
                        camera=scene.camera,
                        date_badge=scene.on_screen_date,
                    )
                elif isinstance(provider, PollinationsAIProvider):
                    result = provider.fetch_video(
                        scene.footage_queries,
                        raw_path,
                        min_duration=scene.duration,
                        ai_prompt=scene.ai_prompt,
                        camera=scene.camera,
                        date_badge=scene.on_screen_date,
                        seed=100 + idx,
                    )
                elif isinstance(provider, CinematicMotionVisualProvider):
                    result = provider.generate_motion_clip(
                        raw_path,
                        title=scene.title,
                        duration=scene.duration,
                        mood=scene.bgm_mood,
                        camera=scene.camera,
                        date_badge=scene.on_screen_date,
                    )
                else:
                    result = provider.fetch_video(scene.footage_queries, raw_path, min_duration=scene.duration)

                if result and os.path.exists(result) and os.path.getsize(result) > 1000:
                    found_path = result
                    source_used = provider.name
                    break

            if not found_path:
                logger.info(f"[{scene.scene_id}] Generating 2D editorial motion backdrop...")
                found_path = self.motion_gen.generate_motion_clip(
                    raw_path,
                    title=scene.title,
                    duration=scene.duration,
                    mood=scene.bgm_mood,
                    camera=scene.camera,
                    date_badge=scene.on_screen_date,
                )
                source_used = "cinematic_motion_generator"

            self._normalize_clip(found_path, normalized_path, scene.duration)

            # Remove temporary raw download after normalization to keep disk footprint lean (for 25-min runs)
            if found_path != normalized_path and os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

            scene.video_asset_path = normalized_path
            scene.asset_source = source_used

        return manifest

    def _normalize_clip(self, input_path: str, output_path: str, target_duration: float):
        """Convert any clip to exact resolution, 25fps, fixed duration, and clean silent video stream."""
        prof = self.config.profile
        vf = (
            f"scale={prof.width}:{prof.height}:force_original_aspect_ratio=decrease,"
            f"pad={prof.width}:{prof.height}:(ow-iw)/2:(oh-ih)/2:#0F172A,"
            f"fps={prof.fps},setsar=1,format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", input_path,
            "-vf", vf,
            "-t", str(target_duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", str(prof.crf),
            "-an",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg normalization failed for {input_path}: {res.stderr[-300:]}")
            emergency_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=#1e293b:s={prof.width}x{prof.height}:r={prof.fps}:d={target_duration}",
                "-t", str(target_duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                output_path,
            ]
            subprocess.run(emergency_cmd, capture_output=True)
