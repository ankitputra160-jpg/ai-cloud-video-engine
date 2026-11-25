"""
engine/qc/inspector.py - Stage H: Automated Quality Inspection Engine
Performs rigorous structural, stream, duration, and frame integrity verification on final video.
"""
import os
import json
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from engine.config import PipelineConfig
from engine.renderer.ffmpeg_utils import get_media_info

logger = logging.getLogger("qc.inspector")

@dataclass
class QCReport:
    passed: bool
    status: str
    target_duration: float
    actual_duration: float
    width: int
    height: int
    fps: float
    has_video_stream: bool
    has_audio_stream: bool
    video_codec: str
    audio_codec: str
    file_size_bytes: int
    black_frame_seconds: float = 0.0
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

class QualityInspector:
    def __init__(self, config: PipelineConfig):
        self.config = config

    def inspect_video(self, video_path: str, expected_duration: float) -> QCReport:
        """Run deep quality inspection on the rendered MP4 file."""
        logger.info(f"Running automated Quality Control on: {video_path}")
        issues: List[str] = []
        warnings: List[str] = []

        if not os.path.exists(video_path):
            return QCReport(
                passed=False, status="FAILED",
                target_duration=expected_duration, actual_duration=0.0,
                width=0, height=0, fps=0.0,
                has_video_stream=False, has_audio_stream=False,
                video_codec="", audio_codec="", file_size_bytes=0,
                issues=["Output video file does not exist!"]
            )

        file_size = os.path.getsize(video_path)
        if file_size < 10000:
            issues.append(f"File size unusually small ({file_size} bytes), possibly truncated.")

        # Probe streams
        probe = get_media_info(video_path)
        streams = probe.get("streams", [])
        fmt = probe.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # 1. Video stream checks
        has_v = video_stream is not None
        v_codec = video_stream.get("codec_name", "") if video_stream else ""
        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0

        if not has_v:
            issues.append("Missing video stream in container.")
        else:
            prof = self.config.profile
            if width != prof.width or height != prof.height:
                warnings.append(f"Resolution mismatch: expected {prof.width}x{prof.height}, got {width}x{height}")

        # 2. Audio stream checks
        has_a = audio_stream is not None
        a_codec = audio_stream.get("codec_name", "") if audio_stream else ""
        if not has_a:
            issues.append("Missing audio stream in container.")

        # 3. FPS checks
        fps = 0.0
        if video_stream and "r_frame_rate" in video_stream:
            r_rate = video_stream["r_frame_rate"]
            try:
                num, den = map(int, r_rate.split('/'))
                fps = round(num / den, 2) if den > 0 else 0.0
            except Exception:
                fps = 25.0

        # 4. Duration checks
        try:
            actual_dur = float(fmt.get("duration", 0.0))
        except (ValueError, TypeError):
            actual_dur = 0.0

        dur_diff = abs(actual_dur - expected_duration)
        if dur_diff > max(3.0, expected_duration * 0.15):
            warnings.append(f"Duration variance: expected {expected_duration}s, actual {actual_dur:.1f}s (diff: {dur_diff:.1f}s)")

        # 5. Black frame check using blackdetect
        black_seconds = self._check_black_frames(video_path)
        if black_seconds > max(1.5, expected_duration * 0.25):
            warnings.append(f"Excessive black frame duration detected ({black_seconds:.1f}s).")

        passed = len(issues) == 0
        status = "PASSED" if passed and len(warnings) == 0 else ("WARNING" if passed else "FAILED")

        report = QCReport(
            passed=passed,
            status=status,
            target_duration=expected_duration,
            actual_duration=round(actual_dur, 2),
            width=width,
            height=height,
            fps=fps,
            has_video_stream=has_v,
            has_audio_stream=has_a,
            video_codec=v_codec,
            audio_codec=a_codec,
            file_size_bytes=file_size,
            black_frame_seconds=round(black_seconds, 2),
            issues=issues,
            warnings=warnings
        )

        logger.info(f"QC Result: {status} (Issues: {len(issues)}, Warnings: {len(warnings)})")
        return report

    def _check_black_frames(self, video_path: str) -> float:
        """Scan video for uninterrupted black frame sequences."""
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", "blackdetect=d=0.5:pix_th=0.10",
            "-f", "null", "-"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            black_dur = 0.0
            for line in res.stderr.splitlines():
                if "black_duration:" in line:
                    parts = line.split("black_duration:")
                    if len(parts) > 1:
                        try:
                            val = float(parts[1].split()[0])
                            black_dur += val
                        except ValueError:
                            pass
            return black_dur
        except Exception:
            return 0.0
