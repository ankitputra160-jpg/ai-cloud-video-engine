"""
tests/test_voice.py - Tests for Voiceover Synthesis, Word-Synced SRT & Hindi ASS Karaoke Subtitles
"""
import os
import tempfile
import unittest
from engine.config import PipelineConfig
from engine.renderer.ffmpeg_utils import get_duration
from engine.storyboard import SceneDefinition, StoryboardManifest
from engine.voice.subtitles import SubtitleGenerator
from engine.voice.tts import VoiceEngine


class TestVoiceEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = PipelineConfig(topic="Test Voice", work_dir=self.temp_dir)
        self.engine = VoiceEngine(self.config)

    def tearDown(self):
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.temp_dir)

    def test_procedural_speech_alignment(self):
        out_wav = os.path.join(self.temp_dir, "procedural.wav")
        self.engine._synthesize_procedural_speech("Exploring the cosmic wonders.", out_wav, duration=4.0)
        self.assertTrue(os.path.exists(out_wav))

        aligned_wav = os.path.join(self.temp_dir, "aligned.wav")
        self.engine._align_audio_duration(out_wav, aligned_wav, target_duration=4.0)
        self.assertTrue(os.path.exists(aligned_wav))
        dur = get_duration(aligned_wav)
        self.assertAlmostEqual(dur, 4.0, delta=0.2)

    def test_srt_and_ass_karaoke_generation(self):
        manifest = StoryboardManifest(
            topic="Space",
            language="hi",
            target_duration=10,
            scenes=[
                SceneDefinition(
                    scene_id="scene_01",
                    chapter_index=1,
                    title="Intro",
                    narration="प्राचीन भारतीय विज्ञान की यह अद्भुत खोज इतिहास बन गई।",
                    visual_description="Stars",
                    footage_queries=["space"],
                    ai_prompt="space prompt",
                    duration=5.0,
                    transition="fade",
                    bgm_mood="epic",
                    sfx_tag="wind",
                    subtitle_text="प्राचीन भारतीय विज्ञान की यह अद्भुत खोज इतिहास बन गई।",
                ),
                SceneDefinition(
                    scene_id="scene_02",
                    chapter_index=2,
                    title="Orbit",
                    narration="आर्यभट्ट ने ग्रहों की गति की सटीक गणना की।",
                    visual_description="Earth",
                    footage_queries=["earth"],
                    ai_prompt="earth prompt",
                    duration=5.0,
                    transition="crossfade",
                    bgm_mood="inspiring",
                    sfx_tag="chime",
                    subtitle_text="आर्यभट्ट ने ग्रहों की गति की सटीक गणना की।",
                ),
            ],
        )

        srt_file = os.path.join(self.temp_dir, "test.srt")
        SubtitleGenerator.generate_srt(manifest, srt_file)
        self.assertTrue(os.path.exists(srt_file))
        with open(srt_file, "r", encoding="utf-8") as f:
            srt_content = f.read()
        self.assertIn("-->", srt_content)
        self.assertIn("प्राचीन भारतीय विज्ञान", srt_content)

        ass_file = os.path.join(self.temp_dir, "test.ass")
        SubtitleGenerator.generate_ass(manifest, ass_file, style_mode="ass_karaoke")
        self.assertTrue(os.path.exists(ass_file))
        with open(ass_file, "r", encoding="utf-8-sig") as f:
            ass_content = f.read()
        self.assertIn("Noto Sans Devanagari", ass_content)
        self.assertIn("\\kf", ass_content)
        self.assertIn("आर्यभट्ट", ass_content)


if __name__ == "__main__":
    unittest.main()
