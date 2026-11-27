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

    def test_fish_cartesia_sarvam_v3_and_waterfall_fallback(self):
        """Verifies Fish Audio MsgPack cloning, Cartesia clone+TTS, Sarvam bulbul:v3, and clean waterfall."""
        import base64
        import io
        import json
        import wave
        from unittest.mock import patch

        # Build minimal valid 1.0s WAV payload bytes in memory
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x01\x00" * 24000)
        sample_wav_bytes = wav_buf.getvalue()

        ref_wav = os.path.join(self.temp_dir, "ref_sample.wav")
        with open(ref_wav, "wb") as f:
            f.write(sample_wav_bytes)

        # 1. Pure-Python MsgPack serializer packs dict + binary reference audio cleanly
        packed = VoiceEngine._pack_msgpack({"text": "नमस्ते", "references": [{"audio": b"\x01\x02", "text": "hi"}]})
        self.assertIsInstance(packed, bytes)
        self.assertIn("नमस्ते".encode("utf-8"), packed)

        seen_requests = []

        class _FakeResp:
            def __init__(self, payload: bytes):
                self._payload = payload

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def _fake_urlopen(req, timeout=30):
            url = req.full_url
            seen_requests.append((url, dict(req.header_items()), req.data))
            if "api.fish.audio" in url:
                return _FakeResp(sample_wav_bytes)
            if "api.cartesia.ai/voices/clone" in url:
                return _FakeResp(json.dumps({"id": "cartesia_vid_abc"}).encode("utf-8"))
            if "api.cartesia.ai/tts/bytes" in url:
                return _FakeResp(sample_wav_bytes)
            if "api.sarvam.ai/text-to-speech" in url:
                b64 = base64.b64encode(sample_wav_bytes).decode("ascii")
                return _FakeResp(json.dumps({"audios": [b64]}).encode("utf-8"))
            raise RuntimeError(f"Unexpected URL: {url}")

        cfg = PipelineConfig(
            topic="Waterfall",
            language="hi",
            work_dir=self.temp_dir,
            fish_api_key="fish_k",
            cartesia_api_key="cart_k",
            sarvam_api_key="sarvam_k",
        )
        ve = VoiceEngine(cfg)

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            out_fish = os.path.join(self.temp_dir, "out_fish.wav")
            self.assertTrue(ve._generate_fish_speech("नमस्ते भारत", out_fish, ref_audio_path=ref_wav, ref_text="राजू"))
            fish_req = seen_requests[-1]
            self.assertEqual(fish_req[1].get("Content-type"), "application/msgpack")
            self.assertEqual(fish_req[1].get("Model"), "s2.1-pro")

            out_cart = os.path.join(self.temp_dir, "out_cart.wav")
            self.assertTrue(ve._generate_cartesia_speech("सुप्रीम कोर्ट", out_cart, ref_audio_path=ref_wav))
            self.assertEqual(ve._cloned_cartesia_voice_id, "cartesia_vid_abc")

            out_sarv = os.path.join(self.temp_dir, "out_sarv.wav")
            self.assertTrue(ve._generate_sarvam_speech("असली सच", out_sarv))
            sarv_body = json.loads(seen_requests[-1][2].decode("utf-8"))
            self.assertEqual(sarv_body["model"], "bulbul:v3")
            self.assertEqual(sarv_body["language_code"], "hi-IN")
            self.assertEqual(sarv_body["speaker"], "kabir")

        # 2. Verify Multi-Provider Waterfall: if Fish raises 429/error, cascades cleanly to Sarvam
        manifest = StoryboardManifest(
            topic="Waterfall E2E",
            language="hi",
            target_duration=5,
            scenes=[
                SceneDefinition(
                    scene_id="scene_01",
                    chapter_index=1,
                    title="Hook",
                    narration="यह असली कहानी है।",
                    visual_description="Court",
                    footage_queries=["court"],
                    ai_prompt="court",
                    duration=3.0,
                    transition="fade",
                    bgm_mood="curious",
                    sfx_tag="soft_whoosh",
                    subtitle_text="यह असली कहानी है।",
                )
            ],
        )
        cfg_wf = PipelineConfig(
            topic="WF",
            language="hi",
            work_dir=os.path.join(self.temp_dir, "wf_ws"),
            voice_engine="fish",
            fish_api_key="fish_k",
            sarvam_api_key="sarvam_k",
        )
        ve_wf = VoiceEngine(cfg_wf)

        def _fish_fails_then_sarvam(req, timeout=30):
            if "api.fish.audio" in req.full_url:
                raise RuntimeError("HTTP 429 quota exceeded")
            b64 = base64.b64encode(sample_wav_bytes).decode("ascii")
            return _FakeResp(json.dumps({"audios": [b64]}).encode("utf-8"))

        with patch("urllib.request.urlopen", side_effect=_fish_fails_then_sarvam):
            out_manifest = ve_wf.synthesize_storyboard_narration(manifest)
        self.assertTrue(os.path.exists(out_manifest.scenes[0].voice_asset_path))
        self.assertGreater(os.path.getsize(out_manifest.scenes[0].voice_asset_path), 4000)

    def test_sarvam_failure_falls_back_to_edge_tts(self):
        """When SARVAM_API_KEY fails or hits quota, Edge-TTS runs automatically before Piper."""
        import wave
        from unittest.mock import patch

        cfg = PipelineConfig(
            topic="Sarvam Fallback",
            language="hi",
            work_dir=os.path.join(self.temp_dir, "sarvam_fb_ws"),
            voice_engine="sarvam",
            sarvam_api_key="bad_or_exhausted_key",
        )
        ve = VoiceEngine(cfg)
        manifest = StoryboardManifest(
            topic="Fallback",
            language="hi",
            target_duration=4,
            scenes=[
                SceneDefinition(
                    scene_id="scene_01",
                    chapter_index=1,
                    title="Hook",
                    narration="सावधान हो जाइए।",
                    visual_description="Phone call",
                    footage_queries=["phone"],
                    ai_prompt="phone",
                    duration=3.0,
                    transition="fade",
                    bgm_mood="mysterious",
                    sfx_tag="deep_sub_hit",
                    subtitle_text="सावधान हो जाइए।",
                )
            ],
        )

        def _fake_edge(text, out_wav):
            with wave.open(out_wav, "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44100)
                w.writeframes(b"\x10\x00\x10\x00" * 44100)
            return True, [{"text": "सावधान", "start": 0.1, "end": 0.5}, {"text": "हो", "start": 0.5, "end": 0.7}, {"text": "जाइए।", "start": 0.7, "end": 1.0}]

        with patch.object(ve, "_generate_sarvam_speech", return_value=False) as mock_sarvam, \
             patch.object(ve, "_generate_edge_speech", side_effect=_fake_edge) as mock_edge, \
             patch.object(ve, "_generate_piper_speech", return_value=False) as mock_piper:
            out_m = ve.synthesize_storyboard_narration(manifest)

        mock_sarvam.assert_called()
        mock_edge.assert_called()
        mock_piper.assert_not_called()
        self.assertTrue(os.path.exists(out_m.scenes[0].voice_asset_path))


if __name__ == "__main__":
    unittest.main()
