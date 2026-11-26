"""
engine/audio/mixer.py - Broadcast-Grade Audio Production & Speech Ducking Mixer
Uses normalize=0 in FFmpeg amix so narration keeps full -14 dB clarity while SFX and
atmospheric BGM remain softly ducked underneath.
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
        sfx_vol: float = 0.09,
        bgm_ducked_vol: float = 0.06,
    ) -> bool:
        """Mix mastered voiceover (full level), subtle ambient SFX, and soft ducked BGM."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        dur = max(1.0, float(duration))

        # normalize=0 is mandatory in amix so FFmpeg does not divide narrator volume by 3!
        filter_complex = (
            f"[0:a]volume={voice_vol}[voice_clean];"
            f"[1:a]volume={sfx_vol}[sfx_clean];"
            f"[2:a]volume={bgm_ducked_vol},lowpass=f=2200,aloop=loop=-1:size=2e+09[bgm_loop];"
            f"[voice_clean][sfx_clean][bgm_loop]amix=inputs=3:duration=first:dropout_transition=2:normalize=0,"
            f"alimiter=limit=0.95[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", voice_path,
            "-i", sfx_path,
            "-i", bgm_path,
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-t", str(dur),
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            output_path,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True

        logger.warning(f"Audio mix fallback triggered: {res.stderr[-250:]}")
        simple_filter = (
            f"[0:a]volume={voice_vol}[v];"
            f"[1:a]volume={sfx_vol}[s];"
            f"[2:a]volume={bgm_ducked_vol},aloop=loop=-1:size=2e+09[b];"
            f"[v][s][b]amix=inputs=3:duration=first:normalize=0[aout]"
        )
        simple_cmd = [
            "ffmpeg", "-y",
            "-i", voice_path,
            "-i", sfx_path,
            "-i", bgm_path,
            "-filter_complex", simple_filter,
            "-map", "[aout]",
            "-t", str(dur),
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            output_path,
        ]
        res_simple = subprocess.run(simple_cmd, capture_output=True)
        return res_simple.returncode == 0
