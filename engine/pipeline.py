"""
engine/pipeline.py - Master Documentary Production Pipeline Orchestrator
Executes Stages A through H sequentially with checkpointing, error recovery, and QC inspection.
"""
import os
import sys
import json
import logging
import time
import argparse
from typing import Optional, Dict, Any

from engine.config import PipelineConfig
from engine.research import ResearchEngine, ResearchDossier
from engine.scriptwriter import ScriptWriter, DocumentaryScript
from engine.storyboard import StoryboardEngine, StoryboardManifest
from engine.assets.manager import VisualAssetManager
from engine.voice.tts import VoiceEngine
from engine.voice.subtitles import SubtitleGenerator
from engine.audio.bgm import BackgroundMusicEngine
from engine.audio.sfx import SoundEffectsEngine
from engine.audio.mixer import AudioProductionMixer
from engine.renderer.editor import VideoEditor
from engine.qc.inspector import QualityInspector, QCReport

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
        logger.info(f"🎬 Starting AI Documentary Production Engine v2.0")
        logger.info(f"📋 Topic: {self.config.topic}")
        logger.info(f"⏱️ Target Duration: {self.config.duration}s | Language: {self.config.language} | Resolution: {self.config.resolution}")
        logger.info(f"{'='*60}")

        # -------------------------------------------------------------
        # STAGE A: Research
        # -------------------------------------------------------------
        logger.info("\n--- STAGE A: Autonomous Topic Research ---")
        research_engine = ResearchEngine(timeout=self.config.http_timeout, language=self.config.language)
        dossier: ResearchDossier = research_engine.search_topic(self.config.topic)
        
        dossier_path = os.path.join(self.work_dir, "research_dossier.json")
        with open(dossier_path, "w", encoding="utf-8") as f:
            json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Research completed: '{dossier.title}' ({len(dossier.key_facts)} facts gathered)")

        # -------------------------------------------------------------
        # STAGE B: Script Generation
        # -------------------------------------------------------------
        logger.info("\n--- STAGE B: Narrative Scriptwriting ---")
        writer = ScriptWriter(language=self.config.language)
        script: DocumentaryScript = writer.generate_script(dossier, self.config.duration)
        
        script_path = os.path.join(self.work_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Script composed: {len(script.chapters)} chapters, {script.total_words} words")

        # -------------------------------------------------------------
        # STAGE C: Storyboard Planning
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
        # STAGE E: Voiceover & Subtitles
        # -------------------------------------------------------------
        logger.info("\n--- STAGE E: AI Narration & Subtitle Generation ---")
        voice_engine = VoiceEngine(self.config)
        manifest = voice_engine.synthesize_storyboard_narration(manifest)

        srt_path = os.path.join(self.work_dir, "subtitles.srt")
        SubtitleGenerator.generate_srt(manifest, srt_path)
        logger.info(f"✅ Subtitles generated: {srt_path}")

        # -------------------------------------------------------------
        # STAGE F: Audio Production & Ducking
        # -------------------------------------------------------------
        logger.info("\n--- STAGE F: Audio Production & Speech Ducking ---")
        audio_dir = os.path.join(self.work_dir, "mastered_audio")
        os.makedirs(audio_dir, exist_ok=True)

        for scene in manifest.scenes:
            # 1. Generate scene-specific thematic BGM
            bgm_scene_path = os.path.join(audio_dir, f"bgm_{scene.scene_id}.wav")
            BackgroundMusicEngine.generate_thematic_bgm(bgm_scene_path, scene.duration, mood=scene.bgm_mood)

            # 2. Generate scene-specific SFX
            sfx_scene_path = os.path.join(audio_dir, f"sfx_{scene.scene_id}.wav")
            SoundEffectsEngine.generate_sfx(scene.sfx_tag, scene.duration, sfx_scene_path)
            scene.sfx_asset_path = sfx_scene_path

            # 3. Mix narration, SFX, and ducked BGM
            mixed_audio_path = os.path.join(audio_dir, f"mixed_{scene.scene_id}.wav")
            AudioProductionMixer.mix_scene_audio(
                voice_path=scene.voice_asset_path,
                sfx_path=sfx_scene_path,
                bgm_path=bgm_scene_path,
                output_path=mixed_audio_path,
                duration=scene.duration
            )
            # Re-assign mixed audio as the scene's audio track
            scene.voice_asset_path = mixed_audio_path

        logger.info("✅ Audio tracks synthesized, ducked, and mixed.")

        # -------------------------------------------------------------
        # STAGE G: Video Editing & Assembly
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
            "elapsed_seconds": elapsed
        }

def main():
    parser = argparse.ArgumentParser(description="AI Documentary Production Engine")
    parser.add_argument("--topic", default="The History of Electric Vehicles", help="Documentary subject")
    parser.add_argument("--style", default="Documentary", help="Visual/Narrative style")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds (10 - 600)")
    parser.add_argument("--language", default="en", choices=["en", "hi"], help="Narration language")
    parser.add_argument("--resolution", default="1080p", choices=["1080p", "4k", "720p"], help="Output resolution")
    parser.add_argument("--output", default="output/final_documentary.mp4", help="Output file path")
    parser.add_argument("--work-dir", default=".workspace", help="Scratch directory for intermediate assets")
    args = parser.parse_args()

    config = PipelineConfig(
        topic=args.topic,
        style=args.style,
        duration=args.duration,
        language=args.language,
        resolution=args.resolution,
        output_path=args.output,
        work_dir=args.work_dir
    )

    pipeline = DocumentaryPipeline(config)
    result = pipeline.run()

    if not result["success"]:
        logger.error("Documentary production finished with QC failures.")
        sys.exit(1)

if __name__ == "__main__":
    main()
