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

        mastered_wav = os.path.join(self.temp_dir, "mastered.wav")
        self.engine._master_voice_track(aligned_wav, mastered_wav)
        self.assertTrue(os.path.exists(mastered_wav))
        self.assertTrue(os.path.getsize(mastered_wav) > 1000)

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

    def test_custom_single_mp3_voice_bank_and_no_speaker_mixing(self):
        """Custom voice file + .txt auto-converts cleanly and blocks synthetic Tapan speaker mixing."""
        import subprocess
        from unittest.mock import patch
        from engine.voice.aligner import ForcedAligner

        bank = os.path.join(self.temp_dir, "custom_bank")
        os.makedirs(bank, exist_ok=True)
        custom_mp3 = os.path.join(bank, "raju.mp3")
        custom_txt = os.path.join(bank, "raju.txt")
        with open(custom_txt, "w", encoding="utf-8") as f:
            f.write("यह राजू की असली आवाज़ का नमूना है।")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=210:duration=12",
            "-ar", "44100", "-ac", "1", custom_mp3,
        ], check=True)

        cfg = PipelineConfig(topic="Clone Check", language="hi", work_dir=self.temp_dir, voice_bank_dir=bank)
        ve = VoiceEngine(cfg)
        with patch.object(ve, "_load_indic_parler") as mock_parler:
            refs = ve.ensure_mood_reference_bank()
            mock_parler.assert_not_called()

        self.assertEqual(set(refs.keys()), {"neutral", "suspense", "angry", "fast"})
        # Single custom voice propagated uniformly across all 4 moods with exact user transcript
        self.assertEqual(refs["suspense"], refs["neutral"])
        self.assertEqual(ve._ref_texts["neutral"], "यह राजू की असली आवाज़ का नमूना है।")
        self.assertEqual(ve._ref_texts["angry"], "यह राजू की असली आवाज़ का नमूना है।")
        # Long 12s MP3 converted cleanly to <=9.5s 24kHz mono WAV
        dur = get_duration(refs["neutral"])
        self.assertLessEqual(dur, 9.6)
        self.assertGreater(dur, 2.0)

        # Verify ForcedAligner word-count mismatch & WordBoundary mapping safety
        mapped_ctc = ForcedAligner.map_ctc_results_to_words(
            ["सुप्रीम", "कोर्ट"],
            [{"start": 0.1, "end": 0.4}, {"start": 0.4, "end": 0.7}, {"start": 0.8, "end": 1.4}],
            audio_duration=2.0,
        )
        self.assertEqual(len(mapped_ctc), 2)
        self.assertAlmostEqual(mapped_ctc[1]["end"], 1.4, delta=0.05)

        wb_mapped = ForcedAligner.align_with_word_boundaries(
            ["भारत", "और", "विज्ञान"],
            [
                {"text": "भारत", "start": 0.1, "end": 0.5},
                {"text": "और", "start": 0.55, "end": 0.8},
                {"text": "विज्ञान", "start": 0.85, "end": 1.6},
            ],
            audio_duration=2.0,
        )
        self.assertEqual(len(wb_mapped), 3)
        self.assertAlmostEqual(wb_mapped[2]["start"], 0.85, delta=0.02)

    def test_elevenlabs_custom_voice_id_and_clone_resolution(self):
        cfg = PipelineConfig(
            topic="EL Check",
            work_dir=self.temp_dir,
            elevenlabs_api_key="test_el_key",
            elevenlabs_voice_id="custom_raju_vid_123",
        )
        ve = VoiceEngine(cfg)
        self.assertEqual(ve._resolve_elevenlabs_voice_id("test_el_key"), "custom_raju_vid_123")


if __name__ == "__main__":
    unittest.main()
