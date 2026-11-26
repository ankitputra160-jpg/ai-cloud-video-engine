"""
engine/audio/mixer.py - Broadcast Audio Mixing, Sidechain Ducking & YouTube -14 LUFS LRA=6 Mastering
Uses FFmpeg `sidechaincompress` so background music automatically ducks beneath narration
and lifts softly during human [pause] gaps, plus optional archive/radio band-pass filtering
(`highpass=f=300,lowpass=f=3000`) on historical quotes and news clips.
"""
import logging
import os
import subprocess

logger = logging.getLogger("audio.mixer")


class AudioProductionMixer:
    @staticmethod
    def mix_scene_audio(
        voice_path: str,
        sfx_path: str,
        bgm_path: str,
        output_path: str,
        duration: float,
        voice_vol: float = 1.0,
        sfx_vol: float = 0.28,
        bgm_vol: float = 0.20,
        archive_quote: bool = False,
    ) -> bool:
        """Mix voiceover (hero level), triggered Foley SFX, and sidechain-ducked BGM."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        dur = max(1.0, float(duration))

        voice_fx = f"volume={voice_vol}"
        if archive_quote:
            # Vintage radio / archival statement character without robotic pitch warping
            voice_fx += ",highpass=f=300,lowpass=f=3000"

        # True sidechain ducking: voice sidechain lowers BGM whenever narrator speaks, lifts on pauses
        filter_complex = (
            f"[0:a]{voice_fx},asplit=2[v_main][v_sc];"
            f"[1:a]volume={sfx_vol}[sfx_clean];"
            f"[2:a]volume={bgm_vol},lowpass=f=2400,aloop=loop=-1:size=2e+09[bgm_raw];"
            f"[bgm_raw][v_sc]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=400[bgm_ducked];"
            f"[v_main][sfx_clean][bgm_ducked]amix=inputs=3:duration=first:dropout_transition=2:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=6,alimiter=limit=0.95[aout]"
        )

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", voice_path,
            "-i", sfx_path,
            "-i", bgm_path,
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-t", f"{dur:.3f}",
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            output_path,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True

        logger.warning(f"Audio sidechain fallback triggered: {res.stderr[-250:]}")
        simple_filter = (
            f"[0:a]{voice_fx}[v];"
            f"[1:a]volume={sfx_vol}[s];"
            f"[2:a]volume={bgm_vol * 0.35:.3f},aloop=loop=-1:size=2e+09[b];"
            f"[v][s][b]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        simple_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", voice_path,
            "-i", sfx_path,
            "-i", bgm_path,
            "-filter_complex", simple_filter,
            "-map", "[aout]",
            "-t", f"{dur:.3f}",
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            output_path,
        ]
        res_simple = subprocess.run(simple_cmd, capture_output=True)
        return res_simple.returncode == 0
