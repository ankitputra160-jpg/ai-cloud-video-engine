"""
engine/pipeline.py - Master Documentary Production Pipeline Orchestrator (v3.0)
Executes Stages A through H with:
  - Fact-Sheet Locking (Research -> fact_sheet.json)
  - 3-Pass Spontaneous Hinglish Script + blader/humanizer Anti-AI Critic + Speak/Show Span-IDs
  - Audio-First Timing Lock (Voice synthesis & CTC forced alignment BEFORE visual cutting -> Zero Drift)
  - Crash-Proof Step-Wise Checkpointing & Auto-Resume (Google Drive compatible)
  - Hybrid Visuals (45% Archival/Real : 25% Playwright News/Map Cards : 25% FLUX : 5% Hero LTX I2V)
  - Hardware NVENC Assembly + Static Devanagari Fonts + Auto-Thumbnail Export
"""
import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict

from engine.assets.manager import VisualAssetManager
from engine.audio.bgm import BackgroundMusicEngine
from engine.audio.mixer import AudioProductionMixer
from engine.audio.sfx import SoundEffectsEngine
from engine.checkpoint import CheckpointManager
from engine.config import (
    PipelineConfig,
    SUPPORTED_LLM_MODES,
    SUPPORTED_SUBTITLE_STYLES,
    SUPPORTED_VOICE_ENGINES,
)
from engine.qc.inspector import QCReport, QualityInspector
from engine.renderer.editor import VideoEditor
from engine.renderer.thumbnail import AutoThumbnailGenerator
from engine.research import ResearchDossier, ResearchEngine
from engine.scriptwriter import DocumentaryScript, ScriptWriter
from engine.storyboard import StoryboardEngine, StoryboardManifest
from engine.voice.subtitles import SubtitleGenerator
from engine.voice.tts import VoiceEngine

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("documentary.pipeline")


class DocumentaryPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.work_dir = config.work_dir
        os.makedirs(self.work_dir, exist_ok=True)
        self.checkpoint = CheckpointManager(self.work_dir)

    def run(self) -> Dict[str, Any]:
        """Execute end-to-end documentary pipeline cleanly with Audio-First timing & resume checkpoints."""
        start_time = time.time()
        logger.info("=" * 60)
        logger.info("🎬 Starting AI Documentary Production Engine v3.0")
        logger.info(f"📋 Topic: {self.config.topic} | Style: {self.config.style} | LLM: {self.config.llm_mode}")
        logger.info(
            f"⏱️ Target: {self.config.duration}s | Lang: {self.config.language} | "
            f"Res: {self.config.resolution} | Preview: {self.config.preview_only}"
        )
        logger.info("=" * 60)

        manifest_path = os.path.join(self.work_dir, "storyboard.json")
        dossier_path = os.path.join(self.work_dir, "research_dossier.json")
        fact_sheet_path = os.path.join(self.work_dir, "fact_sheet.json")
        script_path = os.path.join(self.work_dir, "script.json")

        manifest: StoryboardManifest
        if self.config.storyboard_file and os.path.exists(self.config.storyboard_file):
            logger.info(f"\n--- STAGES A-C: Loading Curated Storyboard ({self.config.storyboard_file}) ---")
            manifest = StoryboardManifest.load_json(self.config.storyboard_file)
            manifest.save_json(manifest_path)
            self.checkpoint.mark_stage_done("storyboard", manifest_path)
        elif self.checkpoint.is_stage_done("storyboard", manifest_path):
            logger.info(f"\n--- CHECKPOINT RESUME: Loading Storyboard from {manifest_path} ---")
            manifest = StoryboardManifest.load_json(manifest_path)
        else:
            # -------------------------------------------------------------
            # STAGE A: Deep Multi-Source Research + Fact-Sheet Lock
            # -------------------------------------------------------------
            logger.info("\n--- STAGE A: Fact-Proof Multi-Source Research ---")
            if self.checkpoint.is_stage_done("research", dossier_path):
                with open(dossier_path, "r", encoding="utf-8") as f:
                    d_data = json.load(f)
                dossier = ResearchDossier(**{k: v for k, v in d_data.items() if k in ResearchDossier.__dataclass_fields__})
                logger.info(f"✅ Resumed Research Dossier: '{dossier.title}'")
            else:
                research_engine = ResearchEngine(timeout=self.config.http_timeout, language=self.config.language)
                dossier = research_engine.search_topic(self.config.topic)
                with open(dossier_path, "w", encoding="utf-8") as f:
                    json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
                dossier.save_fact_sheet(fact_sheet_path)
                self.checkpoint.mark_stage_done("research", dossier_path)
                logger.info(f"✅ Research locked: '{dossier.title}' ({len(dossier.key_facts)} facts, {len(dossier.news_items)} news items)")

            # -------------------------------------------------------------
            # STAGE B: 3-Pass Spontaneous Script + Humanizer Critic + Span-ID
            # -------------------------------------------------------------
            logger.info("\n--- STAGE B: 3-Pass Spontaneous Script & Hindi Humanizer ---")
            writer = ScriptWriter(
                language=self.config.language,
                words_per_minute=self.config.voice_settings.get("words_per_minute", 130),
                style=self.config.style,
                gemini_api_key=self.config.gemini_api_key,
                groq_api_key=self.config.groq_api_key,
                hf_token=self.config.hf_token,
                llm_mode=self.config.llm_mode,
            )
            script: DocumentaryScript = writer.generate_script(dossier, self.config.duration)

            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script.to_dict(), f, indent=2, ensure_ascii=False)
            script_md_path = os.path.join(self.work_dir, "2d_script.md")
            with open(script_md_path, "w", encoding="utf-8") as f:
                f.write(script.to_2d_markdown())
            self.checkpoint.mark_stage_done("script", script_path)
            logger.info(f"✅ Script composed: {len(script.chapters)} beats, {script.total_words} display words")

            # -------------------------------------------------------------
            # STAGE C: HookAndBeatArchitect Dynamic Storyboard Planning
            # -------------------------------------------------------------
            logger.info("\n--- STAGE C: Hook & Beat Hybrid Storyboard Planning ---")
            sb_engine = StoryboardEngine()
            manifest = sb_engine.generate_storyboard(script)
            if self.config.preview_only and len(manifest.scenes) > 3:
                logger.info("⚡ Preview mode active: slicing first 3 hook beats (~30-40s).")
                manifest.scenes = manifest.scenes[:3]
                manifest.target_duration = int(round(manifest.total_duration))
            manifest.save_json(manifest_path)
            self.checkpoint.mark_stage_done("storyboard", manifest_path)
            logger.info(f"✅ Storyboard ready: {len(manifest.scenes)} chapters, planned {manifest.total_duration:.1f}s")

        # -------------------------------------------------------------
        # STAGE D (AUDIO-FIRST): Emotion Voice Synthesis + MMS-300M Sync + Subtitles
        # Runs BEFORE visual cutting so every clip matches exact spoken audio (Zero Drift!)
        # -------------------------------------------------------------
        logger.info("\n--- STAGE D (Audio-First): Expressive Voiceover, CTC Alignment & Subtitles ---")
        voice_engine = VoiceEngine(self.config)
        manifest = voice_engine.synthesize_storyboard_narration(manifest, lock_audio_first=True)

        srt_path = os.path.join(self.work_dir, "subtitles.srt")
        ass_path = os.path.join(self.work_dir, "subtitles.ass")
        SubtitleGenerator.generate_srt(manifest, srt_path)
        SubtitleGenerator.generate_ass(
            manifest,
            ass_path,
            width=self.config.profile.width,
            height=self.config.profile.height,
            style_mode=self.config.subtitle_style,
        )
        manifest.save_json(manifest_path)
        self.checkpoint.mark_stage_done("voice_and_subtitles", manifest_path)
        logger.info(f"✅ Audio-First timing locked ({manifest.total_duration:.2f}s total) & subtitles generated.")

        # -------------------------------------------------------------
        # STAGE E: Hybrid Visual Retrieval, OpenCLIP QC, Cards, FLUX & Hero LTX I2V
        # -------------------------------------------------------------
        logger.info("\n--- STAGE E: Hybrid Visual Asset Pipeline & OpenCLIP QC ---")
        asset_manager = VisualAssetManager(self.config)
        manifest = asset_manager.retrieve_assets_for_storyboard(manifest)
        manifest.save_json(manifest_path)
        self.checkpoint.mark_stage_done("visual_assets", manifest_path)
        logger.info(f"✅ Visual assets verified & frame-locked to {self.config.resolution}")

        # -------------------------------------------------------------
        # STAGE F: Foley SFX Placement & Sidechain Audio Production
        # -------------------------------------------------------------
        logger.info("\n--- STAGE F: Foley SFX & Broadcast -14 LUFS LRA=6 Mixing ---")
        audio_dir = os.path.join(self.work_dir, "mastered_audio")
        os.makedirs(audio_dir, exist_ok=True)
        bgm_bank_dir = getattr(self.config, "bgm_bank_dir", None)

        for idx, scene in enumerate(manifest.scenes):
            mixed_audio_path = os.path.join(audio_dir, f"mixed_{scene.scene_id}.wav")
            if os.path.exists(mixed_audio_path) and os.path.getsize(mixed_audio_path) > 4000 and scene.voice_asset_path == mixed_audio_path:
                continue

            bgm_scene_path = os.path.join(audio_dir, f"bgm_{scene.scene_id}.wav")
            BackgroundMusicEngine.generate_thematic_bgm(
                bgm_scene_path,
                scene.duration,
                mood=scene.bgm_mood,
                bgm_bank_dir=bgm_bank_dir,
                chapter_index=idx,
            )

            sfx_scene_path = os.path.join(audio_dir, f"sfx_{scene.scene_id}.wav")
            SoundEffectsEngine.generate_sfx(
                scene.sfx_tag,
                scene.duration,
                sfx_scene_path,
                visual_beats=getattr(scene, "visual_beats", None),
            )
            scene.sfx_asset_path = sfx_scene_path

            AudioProductionMixer.mix_scene_audio(
                voice_path=scene.voice_asset_path,
                sfx_path=sfx_scene_path,
                bgm_path=bgm_scene_path,
                output_path=mixed_audio_path,
                duration=scene.duration,
                archive_quote=bool(getattr(scene, "is_archive_quote", False)),
            )
            scene.voice_asset_path = mixed_audio_path

            for tmp_wav in (bgm_scene_path, sfx_scene_path):
                if os.path.exists(tmp_wav):
                    try:
                        os.remove(tmp_wav)
                    except OSError:
                        pass

        manifest.save_json(manifest_path)
        self.checkpoint.mark_stage_done("audio_mix", manifest_path)
        logger.info("✅ Audio tracks mixed cleanly with sidechain ducking and Foley SFX.")

        # -------------------------------------------------------------
        # STAGE G: Hardware NVENC / CPU Assembly & Static-Font Subtitle Burn
        # -------------------------------------------------------------
        logger.info("\n--- STAGE G: Video Assembly & Faststart MP4 Packaging ---")
        editor = VideoEditor(self.config)
        final_video = editor.assemble_documentary(manifest, srt_path=srt_path)
        if not final_video or not os.path.exists(final_video):
            raise RuntimeError("Video rendering failed in Stage G.")
        self.checkpoint.mark_stage_done("rendered_video", final_video)

        # -------------------------------------------------------------
        # STAGE H: Quality Control Inspection & Auto-Thumbnail Export
        # -------------------------------------------------------------
        logger.info("\n--- STAGE H: Quality Inspection & Auto-Thumbnail ---")
        qc_inspector = QualityInspector(self.config)
        qc_report: QCReport = qc_inspector.inspect_video(final_video, expected_duration=manifest.total_duration)
        qc_path = os.path.join(self.work_dir, "qc_report.json")
        qc_report.save_json(qc_path)

        thumb_out = None
        if self.config.generate_thumbnail and self.config.thumbnail_path:
            hook_line = manifest.scenes[0].narration if manifest.scenes else self.config.topic
            thumb_out = AutoThumbnailGenerator.generate_thumbnail(
                final_video,
                hook_text=hook_line,
                output_jpg_path=self.config.thumbnail_path,
                duration=qc_report.actual_duration or manifest.total_duration,
            )

        elapsed = time.time() - start_time
        logger.info("\n" + "=" * 60)
        logger.info(f"🏆 DOCUMENTARY PRODUCTION COMPLETED in {elapsed:.1f}s")
        logger.info(f"📁 Video: {final_video} ({qc_report.file_size_bytes // 1024} KB)")
        if thumb_out:
            logger.info(f"🖼️ Thumbnail: {thumb_out}")
        logger.info(f"⏱️ Actual Duration: {qc_report.actual_duration:.2f}s (Locked: {manifest.total_duration:.2f}s)")
        logger.info(f"📊 QC Status: {qc_report.status}")
        logger.info("=" * 60 + "\n")

        return {
            "success": qc_report.passed,
            "video_path": final_video,
            "thumbnail_path": thumb_out,
            "qc_report": qc_report.to_dict(),
            "manifest": manifest.to_dict(),
            "elapsed_seconds": elapsed,
        }


def main():
    parser = argparse.ArgumentParser(description="AI Documentary Production Engine v3.0")
    parser.add_argument("--topic", default="The History of Electric Vehicles", help="Documentary subject")
    parser.add_argument("--style", default="Documentary", help="Visual/Narrative style")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds (10 - 1500)")
    parser.add_argument("--language", default="en", choices=["en", "hi"], help="Narration language")
    parser.add_argument("--resolution", default="1080p", choices=["1080p", "4k", "720p"], help="Output resolution")
    parser.add_argument("--subtitle-style", default="ass_karaoke", choices=list(SUPPORTED_SUBTITLE_STYLES), help="Subtitle render preset")
    parser.add_argument("--voice-engine", default="auto", choices=list(SUPPORTED_VOICE_ENGINES), help="Voice synthesizer")
    parser.add_argument("--llm-mode", default="auto", choices=list(SUPPORTED_LLM_MODES), help="LLM script backend")
    parser.add_argument("--storyboard-file", default=None, help="Optional pre-curated storyboard JSON path")
    parser.add_argument("--voice-bank-dir", default=None, help="Directory holding ref_neutral/suspense/angry/fast WAVs")
    parser.add_argument("--bgm-bank-dir", default=None, help="Directory holding 4-mood CC0 BGM folders")
    parser.add_argument("--preview-only", action="store_true", help="Render fast 3-beat Hook preview before full 25m render")
    parser.add_argument("--no-ai-video", action="store_true", help="Skip LTX-Video I2V hook generation")
    parser.add_argument("--thumbnail", default=None, help="Output thumbnail JPG path")
    parser.add_argument("--output", default="output/final_documentary.mp4", help="Output file path")
    parser.add_argument("--work-dir", default=".workspace", help="Scratch/checkpoint directory")
    args = parser.parse_args()

    config = PipelineConfig(
        topic=args.topic,
        style=args.style,
        duration=args.duration,
        language=args.language,
        resolution=args.resolution,
        subtitle_style=args.subtitle_style,
        voice_engine=args.voice_engine,
        llm_mode=args.llm_mode,
        storyboard_file=args.storyboard_file,
        voice_bank_dir=args.voice_bank_dir,
        bgm_bank_dir=args.bgm_bank_dir,
        enable_ai_video=(not args.no_ai_video),
        preview_only=args.preview_only,
        thumbnail_path=args.thumbnail,
        output_path=args.output,
        work_dir=args.work_dir,
    )

    pipeline = DocumentaryPipeline(config)
    result = pipeline.run()

    if not result["success"]:
        logger.error("Documentary production finished with QC failures.")
        sys.exit(1)


if __name__ == "__main__":
    main()
