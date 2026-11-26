"""
engine/pipeline.py - Master Documentary Production Pipeline Orchestrator
Executes Stages A through H sequentially with long-form 25-min support, 2D Video Script mode,
Devanagari-safe word-synced subtitles, and QC verification.
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
from engine.config import PipelineConfig, SUPPORTED_SUBTITLE_STYLES
from engine.qc.inspector import QCReport, QualityInspector
from engine.renderer.editor import VideoEditor
from engine.research import ResearchDossier, ResearchEngine
from engine.scriptwriter import DocumentaryScript, ScriptWriter
from engine.storyboard import StoryboardEngine, StoryboardManifest
from engine.voice.subtitles import SubtitleGenerator
from engine.voice.tts import VoiceEngine

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("documentary.pipeline")


class DocumentaryPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.work_dir = config.work_dir
        os.makedirs(self.work_dir, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        """Execute the full end-to-end documentary production workflow."""
        start_time = time.time()
        logger.info(f"{'='*60}")
        logger.info("🎬 Starting AI Documentary Production Engine v2.5")
        logger.info(f"📋 Topic: {self.config.topic} | Style: {self.config.style}")
        logger.info(f"⏱️ Target Duration: {self.config.duration}s | Language: {self.config.language} | Resolution: {self.config.resolution}")
        logger.info(f"{'='*60}")

        # -------------------------------------------------------------
        # STAGE A: Deep Multi-Source Research
        # -------------------------------------------------------------
        logger.info("\n--- STAGE A: Deep Multi-Source Topic Research ---")
        research_engine = ResearchEngine(timeout=self.config.http_timeout, language=self.config.language)
        dossier: ResearchDossier = research_engine.search_topic(self.config.topic)

        dossier_path = os.path.join(self.work_dir, "research_dossier.json")
        with open(dossier_path, "w", encoding="utf-8") as f:
            json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Research completed: '{dossier.title}' ({len(dossier.key_facts)} facts gathered)")

        # -------------------------------------------------------------
        # STAGE B: Documentary & 2D Script Generation
        # -------------------------------------------------------------
        logger.info("\n--- STAGE B: Narrative & 2D Scriptwriting ---")
        writer = ScriptWriter(
            language=self.config.language,
            words_per_minute=self.config.voice_settings.get("words_per_minute", 130),
            style=self.config.style,
            gemini_api_key=self.config.gemini_api_key,
            groq_api_key=self.config.groq_api_key,
        )
        script: DocumentaryScript = writer.generate_script(dossier, self.config.duration)

        script_path = os.path.join(self.work_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script.to_dict(), f, indent=2, ensure_ascii=False)

        script_md_path = os.path.join(self.work_dir, "2d_script.md")
        with open(script_md_path, "w", encoding="utf-8") as f:
            f.write(script.to_2d_markdown())

        logger.info(f"✅ Script composed: {len(script.chapters)} scenes, {script.total_words} words")

        # -------------------------------------------------------------
        # STAGE C: Dynamic Storyboard Planning
        # -------------------------------------------------------------
        logger.info("\n--- STAGE C: Dynamic Storyboard Schema Planning ---")
        sb_engine = StoryboardEngine()
        manifest: StoryboardManifest = sb_engine.generate_storyboard(script)

        manifest_path = os.path.join(self.work_dir, "storyboard.json")
        manifest.save_json(manifest_path)
        logger.info(f"✅ Storyboard created: {len(manifest.scenes)} scenes, total {manifest.total_duration:.1f}s")

        # -------------------------------------------------------------
        # STAGE D: Visual Asset Generation & Retrieval
        # -------------------------------------------------------------
        logger.info("\n--- STAGE D: Visual Asset Retrieval & Normalization ---")
        asset_manager = VisualAssetManager(self.config)
        manifest = asset_manager.retrieve_assets_for_storyboard(manifest)
        logger.info(f"✅ All visual assets verified and normalized to {self.config.resolution}")

        # -------------------------------------------------------------
        # STAGE E: Voiceover & Word-Synced Subtitles
        # -------------------------------------------------------------
        logger.info("\n--- STAGE E: AI Narration & Word-Synced Subtitle Generation ---")
        voice_engine = VoiceEngine(self.config)
        manifest = voice_engine.synthesize_storyboard_narration(manifest)

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
        logger.info(f"✅ Subtitles generated: {srt_path} & {ass_path}")

        # -------------------------------------------------------------
        # STAGE F: Audio Production & Ducking
        # -------------------------------------------------------------
        logger.info("\n--- STAGE F: Audio Production & Speech Ducking ---")
        audio_dir = os.path.join(self.work_dir, "mastered_audio")
        os.makedirs(audio_dir, exist_ok=True)

        for scene in manifest.scenes:
            bgm_scene_path = os.path.join(audio_dir, f"bgm_{scene.scene_id}.wav")
            BackgroundMusicEngine.generate_thematic_bgm(bgm_scene_path, scene.duration, mood=scene.bgm_mood)

            sfx_scene_path = os.path.join(audio_dir, f"sfx_{scene.scene_id}.wav")
            SoundEffectsEngine.generate_sfx(scene.sfx_tag, scene.duration, sfx_scene_path)
            scene.sfx_asset_path = sfx_scene_path

            mixed_audio_path = os.path.join(audio_dir, f"mixed_{scene.scene_id}.wav")
            AudioProductionMixer.mix_scene_audio(
                voice_path=scene.voice_asset_path,
                sfx_path=sfx_scene_path,
                bgm_path=bgm_scene_path,
                output_path=mixed_audio_path,
                duration=scene.duration,
            )
            scene.voice_asset_path = mixed_audio_path

            # Clean raw intermediate BGM/SFX wavs immediately for 25-min storage safety
            for tmp_wav in (bgm_scene_path, sfx_scene_path):
                if os.path.exists(tmp_wav):
                    try:
                        os.remove(tmp_wav)
                    except OSError:
                        pass

        logger.info("✅ Audio tracks synthesized, ducked, and mixed.")

        # -------------------------------------------------------------
        # STAGE G: Parallel Scene Assembly & Faststart MP4 Packaging
        # -------------------------------------------------------------
        logger.info("\n--- STAGE G: Timeline Assembly & Subtitle Burning ---")
        editor = VideoEditor(self.config)
        final_video = editor.assemble_documentary(manifest, srt_path=srt_path)

        if not final_video or not os.path.exists(final_video):
            raise RuntimeError("Video rendering failed in Stage G.")

        # -------------------------------------------------------------
        # STAGE H: Automated Quality Inspection (QC)
        # -------------------------------------------------------------
        logger.info("\n--- STAGE H: Quality Inspection & Verification ---")
        qc_inspector = QualityInspector(self.config)
        qc_report: QCReport = qc_inspector.inspect_video(final_video, expected_duration=manifest.total_duration)

        qc_path = os.path.join(self.work_dir, "qc_report.json")
        qc_report.save_json(qc_path)

        elapsed = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"🏆 DOCUMENTARY PRODUCTION COMPLETED in {elapsed:.1f}s")
        logger.info(f"📁 Video: {final_video} ({qc_report.file_size_bytes // 1024} KB)")
        logger.info(f"⏱️ Actual Duration: {qc_report.actual_duration:.1f}s (Target: {self.config.duration}s)")
        logger.info(f"📊 QC Status: {qc_report.status}")
        logger.info(f"{'='*60}\n")

        return {
            "success": qc_report.passed,
            "video_path": final_video,
            "qc_report": qc_report.to_dict(),
            "manifest": manifest.to_dict(),
            "elapsed_seconds": elapsed,
        }


def main():
    parser = argparse.ArgumentParser(description="AI Documentary Production Engine")
    parser.add_argument("--topic", default="The History of Electric Vehicles", help="Documentary subject")
    parser.add_argument("--style", default="Documentary", help="Visual/Narrative style (Documentary, 2D Animation, Vox Explainer, Historical, Scientific)")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds (10 - 1500, up to 25 minutes)")
    parser.add_argument("--language", default="en", choices=["en", "hi"], help="Narration language")
    parser.add_argument("--resolution", default="1080p", choices=["1080p", "4k", "720p"], help="Output resolution")
    parser.add_argument("--subtitle-style", default="ass_karaoke", choices=list(SUPPORTED_SUBTITLE_STYLES), help="Subtitle render preset")
    parser.add_argument("--output", default="output/final_documentary.mp4", help="Output file path")
    parser.add_argument("--work-dir", default=".workspace", help="Scratch directory for intermediate assets")
    args = parser.parse_args()

    config = PipelineConfig(
        topic=args.topic,
        style=args.style,
        duration=args.duration,
        language=args.language,
        resolution=args.resolution,
        subtitle_style=args.subtitle_style,
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
