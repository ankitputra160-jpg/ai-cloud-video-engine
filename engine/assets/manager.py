"""
engine/assets/manager.py - Hybrid Visual Asset Orchestrator (45% Real : 25% Cards : 25% AI Still : 5% Hero I2V)
Executes strict Stage-Gate GPU loading/unloading:
  - Stage 3: Watermark-free retrieval (PIB, Archive.org, Openverse, Wikimedia, NASA, Pexels, Pixabay)
             + Dimension QC + OpenCLIP Semantic QC -> Unload OpenCLIP (VRAM: 0 GB)
             + Playwright / libass Investigative News, Quote, Map & Stat Cards
  - Stage 4: FLUX.1-schnell (or Pollinations/2D Card fallback) -> Unload FLUX (VRAM: 0 GB)
  - Stage 5: LTX-Video 0.9.7-distilled FP8 (5% Hero/Chapter Opening I2V) -> Unload LTX (VRAM: 0 GB)
Syncs sub-beat clips precisely to Audio-First locked duration (0.001s precision, zero frame drift).
"""
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Set

from engine.assets.ai_gpu_visuals import FluxStillGenerator, LtxVideoGenerator
from engine.assets.ai_visuals import CinematicMotionVisualProvider
from engine.assets.archive_org import InternetArchiveProvider
from engine.assets.base import VisualAssetProvider
from engine.assets.nasa import NasaMediaProvider
from engine.assets.news_card import InvestigativeCardGenerator
from engine.assets.openverse import OpenverseProvider
from engine.assets.pexels import PexelsProvider
from engine.assets.pib import PIBIndiaProvider
from engine.assets.pixabay import PixabayProvider
from engine.assets.pollinations import PollinationsAIProvider
from engine.assets.qc_visual import SemanticClipChecker, validate_visual_dimensions
from engine.assets.wikimedia import WikimediaCommonsProvider
from engine.config import PipelineConfig
from engine.renderer.ffmpeg_utils import get_duration
from engine.storyboard import StoryboardManifest

logger = logging.getLogger("assets.manager")


class VisualAssetManager:
    def __init__(self, config: PipelineConfig):
        self.config = config
        w, h, fps = config.profile.width, config.profile.height, config.profile.fps
        hf_tok = getattr(config, "hf_token", None)

        self.pib = PIBIndiaProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.archive_org = InternetArchiveProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.openverse = OpenverseProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.wikimedia = WikimediaCommonsProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.nasa = NasaMediaProvider(timeout=config.http_timeout, width=w, height=h, fps=fps)
        self.pexels = PexelsProvider(api_key=config.pexels_api_key, timeout=config.http_timeout)
        self.pixabay = PixabayProvider(api_key=config.pixabay_api_key, timeout=config.http_timeout)
        self.pollinations = PollinationsAIProvider(timeout=max(20, config.http_timeout), width=w, height=h, fps=fps)
        self.motion_gen = CinematicMotionVisualProvider(width=w, height=h, fps=fps)
        self.card_gen = InvestigativeCardGenerator(width=w, height=h, fps=fps)

        self.clip_qc = SemanticClipChecker()
        self.flux_gen = FluxStillGenerator(hf_token=hf_tok, width=w, height=h, fps=fps)
        self.ltx_gen = LtxVideoGenerator(hf_token=hf_tok, width=w, height=h, fps=fps)

        self.real_providers: List[VisualAssetProvider] = [
            self.pib,
            self.wikimedia,
            self.openverse,
            self.archive_org,
            self.nasa,
            self.pexels,
            self.pixabay,
        ]

        self.assets_dir = os.path.join(config.work_dir, "visual_assets")
        os.makedirs(self.assets_dir, exist_ok=True)

    def retrieve_assets_for_storyboard(self, manifest: StoryboardManifest) -> StoryboardManifest:
        """Execute Stage-Gate retrieval, cards, FLUX, and Hero I2V, locked to Audio-First scene durations."""
        logger.info(
            f"Retrieving visual assets for {len(manifest.scenes)} scenes "
            f"(2D Mode: {self.config.is_2d_style}, GPU FLUX: {self.flux_gen.is_available()})..."
        )
        used_urls: Set[str] = set()
        pending_ai_stills: List[Dict[str, Any]] = []
        pending_hero_i2v: List[Dict[str, Any]] = []

        # ------------------------------------------------------------------
        # STAGE 3: Curated + Watermark-Free Stock + OpenCLIP QC + Cards
        # ------------------------------------------------------------------
        for s_idx, scene in enumerate(manifest.scenes):
            normalized_scene_mp4 = os.path.join(self.assets_dir, f"norm_{scene.scene_id}.mp4")

            # Resume checkpoint hit: skip if normalized scene already matches locked duration
            if os.path.exists(normalized_scene_mp4) and os.path.getsize(normalized_scene_mp4) > 10_000:
                existing_dur = get_duration(normalized_scene_mp4)
                if abs(existing_dur - scene.duration) <= 0.15:
                    scene.video_asset_path = normalized_scene_mp4
                    scene.asset_source = scene.asset_source or "checkpoint_cached"
                    continue

            beats = getattr(scene, "visual_beats", None) or [
                {
                    "beat_id": f"{scene.scene_id}_b1",
                    "visual_type": getattr(scene, "visual_type", "real_photo"),
                    "duration": scene.duration,
                    "camera": scene.camera,
                    "query": (scene.footage_queries[0] if scene.footage_queries else scene.title),
                    "ai_prompt": scene.ai_prompt,
                    "headline": getattr(scene, "news_headline", "") or scene.title,
                    "source": getattr(scene, "news_source", "") or "Public Record",
                    "date_badge": scene.on_screen_date,
                }
            ]
            scene.visual_beats = beats

            for b_idx, beat in enumerate(beats):
                b_id = beat.get("beat_id", f"{scene.scene_id}_b{b_idx + 1}")
                beat_raw = os.path.join(self.assets_dir, f"raw_{b_id}.mp4")
                beat_norm = os.path.join(self.assets_dir, f"norm_{b_id}.mp4")
                vtype = str(beat.get("visual_type", "real_photo"))
                b_dur = float(beat.get("duration", scene.duration))

                if os.path.exists(beat_norm) and os.path.getsize(beat_norm) > 5000:
                    beat["asset_path"] = beat_norm
                    continue

                # 1. Explicit curated URL always prioritized on beat 0
                if b_idx == 0 and getattr(scene, "preferred_media_url", None):
                    direct = self.wikimedia.fetch_direct_url_as_video(
                        scene.preferred_media_url,
                        beat_raw,
                        duration=b_dur,
                        camera=beat.get("camera", scene.camera),
                        date_badge=beat.get("date_badge", scene.on_screen_date),
                    )
                    if direct and validate_visual_dimensions(direct, min_width=640, min_height=360):
                        self._normalize_clip(direct, beat_norm, b_dur)
                        self._safe_remove(direct)
                        beat["asset_path"] = beat_norm
                        scene.asset_source = "curated_archival_media"
                        continue

                # 2. Playwright / libass 2D Investigative Cards (25%)
                if vtype in ("news_card", "quote_card", "map_card", "stat_card"):
                    card_res = self.card_gen.render_card_video(
                        beat_raw,
                        card_type=vtype,
                        headline=str(beat.get("headline") or scene.title),
                        source=str(beat.get("source") or "Archival Record"),
                        date_badge=str(beat.get("date_badge") or scene.on_screen_date),
                        duration=b_dur,
                        camera=beat.get("camera", scene.camera),
                    )
                    if card_res and os.path.exists(card_res):
                        self._normalize_clip(card_res, beat_norm, b_dur)
                        self._safe_remove(card_res)
                        beat["asset_path"] = beat_norm
                        continue

                # 3. Defer pure AI Still & Hero I2V beats to dedicated GPU Stages 4 & 5
                if vtype == "hero_ltx_i2v" and getattr(self.config, "enable_ai_video", True) and self.ltx_gen.is_available():
                    pending_hero_i2v.append({"scene": scene, "beat": beat, "raw": beat_raw, "norm": beat_norm, "seed": 200 + s_idx * 10 + b_idx})
                    continue

                if vtype in ("ai_image", "hero_ltx_i2v") or self.config.is_2d_style:
                    pending_ai_stills.append({"scene": scene, "beat": beat, "raw": beat_raw, "norm": beat_norm, "seed": 100 + s_idx * 10 + b_idx})
                    continue

                # 4. Real archival / CC0 photo retrieval + Dimension QC + OpenCLIP QC
                found_real = self._fetch_verified_real_beat(
                    queries=([str(beat.get("query"))] if beat.get("query") else []) + list(scene.footage_queries),
                    prompt_en=str(beat.get("ai_prompt") or scene.ai_prompt),
                    raw_path=beat_raw,
                    duration=b_dur,
                    camera=str(beat.get("camera", scene.camera)),
                    date_badge=str(beat.get("date_badge", scene.on_screen_date)),
                    used_urls=used_urls,
                )
                if found_real:
                    self._normalize_clip(found_real, beat_norm, b_dur)
                    self._safe_remove(found_real)
                    beat["asset_path"] = beat_norm
                else:
                    # Fallback cleanly to FLUX/AI stage
                    pending_ai_stills.append({"scene": scene, "beat": beat, "raw": beat_raw, "norm": beat_norm, "seed": 300 + s_idx * 10 + b_idx})

        # Unload OpenCLIP before FLUX & LTX load (Stage-Gate VRAM=0)
        self.clip_qc.unload()

        # ------------------------------------------------------------------
        # STAGE 4: FLUX.1-schnell AI Stills (or Pollinations / 2D Card fallback)
        # ------------------------------------------------------------------
        for item in pending_ai_stills:
            scene = item["scene"]
            beat = item["beat"]
            b_dur = float(beat.get("duration", scene.duration))
            raw_path = item["raw"]
            norm_path = item["norm"]
            prompt_en = str(beat.get("ai_prompt") or scene.ai_prompt)

            res = None
            if self.flux_gen.is_available():
                res = self.flux_gen.generate_still_clip(
                    prompt_en, raw_path, duration=b_dur, camera=beat.get("camera", scene.camera),
                    date_badge=beat.get("date_badge", ""), seed=item["seed"],
                )
            if not res:
                res = self.pollinations.fetch_video(
                    scene.footage_queries, raw_path, min_duration=b_dur, ai_prompt=prompt_en,
                    camera=beat.get("camera", scene.camera), date_badge=beat.get("date_badge", ""), seed=item["seed"],
                )
            if not res:
                res = self.motion_gen.generate_motion_clip(
                    raw_path, title=str(beat.get("headline") or scene.title), duration=b_dur,
                    mood=scene.bgm_mood, camera=beat.get("camera", scene.camera),
                    date_badge=str(beat.get("date_badge") or scene.on_screen_date),
                )
            if res and os.path.exists(res):
                self._normalize_clip(res, norm_path, b_dur)
                self._safe_remove(res)
                beat["asset_path"] = norm_path

        # Unload FLUX cleanly after generating keyframes (Stage-Gate VRAM=0)
        # Keep keyframe image files only for hero I2V beats
        hero_keyframes: Dict[str, str] = {}
        for h_item in pending_hero_i2v:
            kf_png = h_item["raw"] + ".kf.png"
            if self.flux_gen.is_available():
                if self.flux_gen.generate_image_file(str(h_item["beat"].get("ai_prompt") or h_item["scene"].ai_prompt), kf_png, seed=h_item["seed"]):
                    hero_keyframes[h_item["raw"]] = kf_png
        self.flux_gen.unload()

        # ------------------------------------------------------------------
        # STAGE 5: LTX-Video Distilled FP8 I2V strictly on ~5% Hero Hooks
        # ------------------------------------------------------------------
        for h_item in pending_hero_i2v:
            scene = h_item["scene"]
            beat = h_item["beat"]
            b_dur = float(beat.get("duration", scene.duration))
            raw_path = h_item["raw"]
            norm_path = h_item["norm"]
            kf = hero_keyframes.get(raw_path)
            res = None
            if kf and os.path.exists(kf):
                res = self.ltx_gen.generate_i2v_clip(
                    kf, str(beat.get("ai_prompt") or scene.visual_description), raw_path, seed=h_item["seed"]
                )
                self._safe_remove(kf)
            if not res:
                res = self.motion_gen.generate_motion_clip(
                    raw_path, title=scene.title, duration=b_dur, mood=scene.bgm_mood,
                    camera="push_in", date_badge=scene.on_screen_date,
                )
            if res and os.path.exists(res):
                self._normalize_clip(res, norm_path, b_dur)
                self._safe_remove(res)
                beat["asset_path"] = norm_path
        self.ltx_gen.unload()

        # ------------------------------------------------------------------
        # Assemble beat sub-cuts cleanly into each scene's normalized MP4
        # ------------------------------------------------------------------
        for scene in manifest.scenes:
            normalized_scene_mp4 = os.path.join(self.assets_dir, f"norm_{scene.scene_id}.mp4")
            if os.path.exists(normalized_scene_mp4) and os.path.getsize(normalized_scene_mp4) > 10_000 and scene.video_asset_path == normalized_scene_mp4:
                continue

            beat_files = [
                b["asset_path"] for b in (scene.visual_beats or [])
                if b.get("asset_path") and os.path.exists(b["asset_path"])
            ]
            if len(beat_files) > 1:
                self._concat_beat_clips(beat_files, normalized_scene_mp4, scene.duration)
            elif len(beat_files) == 1:
                self._normalize_clip(beat_files[0], normalized_scene_mp4, scene.duration)
            else:
                fallback_raw = os.path.join(self.assets_dir, f"fb_{scene.scene_id}.mp4")
                self.motion_gen.generate_motion_clip(
                    fallback_raw, title=scene.title, duration=scene.duration, mood=scene.bgm_mood,
                    camera=scene.camera, date_badge=scene.on_screen_date,
                )
                self._normalize_clip(fallback_raw, normalized_scene_mp4, scene.duration)
                self._safe_remove(fallback_raw)

            for bf in beat_files:
                self._safe_remove(bf)

            scene.video_asset_path = normalized_scene_mp4
            if not scene.asset_source:
                scene.asset_source = "hybrid_visual_pipeline"

        return manifest

    def _fetch_verified_real_beat(
        self,
        queries: List[str],
        prompt_en: str,
        raw_path: str,
        duration: float,
        camera: str,
        date_badge: str,
        used_urls: Set[str],
    ) -> Optional[str]:
        for provider in self.real_providers:
            if not provider.is_available():
                continue
            if isinstance(provider, NasaMediaProvider) and not provider.is_topic_relevant(queries):
                continue
            if isinstance(provider, PIBIndiaProvider) and not provider.is_topic_relevant(queries):
                continue

            if isinstance(provider, (WikimediaCommonsProvider, PIBIndiaProvider, InternetArchiveProvider, OpenverseProvider)):
                res = provider.fetch_video(
                    queries, raw_path, min_duration=duration, used_urls=used_urls,
                    camera=camera, date_badge=date_badge,
                    **({"prefer_images": self.config.is_2d_style} if isinstance(provider, WikimediaCommonsProvider) else {}),
                )
            elif isinstance(provider, NasaMediaProvider):
                res = provider.fetch_video(
                    queries, raw_path, min_duration=duration, used_urls=used_urls,
                    camera=camera, date_badge=date_badge,
                )
            else:
                res = provider.fetch_video(queries, raw_path, min_duration=duration)

            if not res or not os.path.exists(res) or os.path.getsize(res) < 5000:
                continue
            if not validate_visual_dimensions(res, min_width=960, min_height=540):
                self._safe_remove(res)
                continue

            # On Colab GPU, extract mid-frame and verify OpenCLIP semantic score
            if self.clip_qc.is_available():
                frame_chk = res + ".chk.jpg"
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", res, "-vframes", "1", frame_chk],
                    capture_output=True,
                )
                ok_sem = (not os.path.exists(frame_chk)) or self.clip_qc.passes_semantic_check(frame_chk, prompt_en)
                self._safe_remove(frame_chk)
                if not ok_sem:
                    self._safe_remove(res)
                    continue
            return res
        return None

    def _concat_beat_clips(self, beat_files: List[str], output_path: str, exact_duration: float):
        list_txt = output_path + ".beats.txt"
        with open(list_txt, "w", encoding="utf-8") as f:
            for p in beat_files:
                abs_p = os.path.abspath(p).replace("'", "'\\''")
                f.write(f"file '{abs_p}'\n")
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", list_txt,
            "-t", f"{exact_duration:.3f}",
            "-c:v", "copy", "-an",
            output_path,
        ]
        res = subprocess.run(cmd, capture_output=True)
        self._safe_remove(list_txt)
        if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 5000:
            self._normalize_clip(beat_files[0], output_path, exact_duration)

    def _normalize_clip(self, input_path: str, output_path: str, target_duration: float):
        """Normalize resolution, exact FPS, pixel format, and 0.001s Audio-First target duration."""
        prof = self.config.profile
        vf = (
            f"scale={prof.width}:{prof.height}:force_original_aspect_ratio=decrease,"
            f"pad={prof.width}:{prof.height}:(ow-iw)/2:(oh-ih)/2:#0F172A,"
            f"fps={prof.fps},setsar=1,format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-stream_loop", "-1",
            "-i", input_path,
            "-vf", vf,
            "-t", f"{target_duration:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(prof.crf),
            "-an", output_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg normalization failed for {input_path}: {res.stderr[-250:]}")
            emergency_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi",
                "-i", f"color=c=#1e293b:s={prof.width}x{prof.height}:r={prof.fps}:d={target_duration:.3f}",
                "-t", f"{target_duration:.3f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                output_path,
            ]
            subprocess.run(emergency_cmd, capture_output=True)

    @staticmethod
    def _safe_remove(path: Optional[str]) -> None:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
