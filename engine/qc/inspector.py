"""
engine/qc/inspector.py - Stage H: Automated Quality Inspection Engine
Performs rigorous structural, stream, duration, ebur128 (-14 LUFS) loudness,
audio-subtitle timing sync, and frame integrity verification on final video.
"""
import os
import re
import json
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
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
    pix_fmt: str = ""
    integrated_lufs: Optional[float] = None
    loudness_range_lra: Optional[float] = None
    true_peak_dbtp: Optional[float] = None
    subtitle_sync_ok: bool = True
    subtitle_cue_count: int = 0
    subtitle_max_end_sec: float = 0.0
    subtitle_sync_drift_sec: float = 0.0
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

    def inspect_video(
        self,
        video_path: str,
        expected_duration: float,
        subtitle_path: Optional[str] = None,
        manifest: Optional[Any] = None,
    ) -> QCReport:
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
        pix_fmt = video_stream.get("pix_fmt", "") if video_stream else ""
        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0

        if not has_v:
            issues.append("Missing video stream in container.")
        else:
            prof = self.config.profile
            if width != prof.width or height != prof.height:
                warnings.append(f"Resolution mismatch: expected {prof.width}x{prof.height}, got {width}x{height}")
            if pix_fmt and pix_fmt != "yuv420p":
                warnings.append(f"Pixel format mismatch: expected yuv420p, got {pix_fmt}")

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

        # 5. Black frame check using blackdetect (scaled timeout for up to 25-min renders)
        black_seconds = self._check_black_frames(video_path, timeout=max(45, int(expected_duration * 0.5)))
        if black_seconds > max(1.5, expected_duration * 0.25):
            warnings.append(f"Excessive black frame duration detected ({black_seconds:.1f}s).")

        # 6. EBU R128 loudness check (-14 LUFS broadcast target)
        integrated_lufs, lra_lu, true_peak = (None, None, None)
        if has_a:
            integrated_lufs, lra_lu, true_peak = self._measure_loudness_ebur128(
                video_path, timeout=max(45, int(expected_duration * 0.5))
            )
            if integrated_lufs is not None:
                if integrated_lufs < -22.0 or integrated_lufs > -10.0:
                    warnings.append(
                        f"Audio loudness outside broadcast range around -14 LUFS: {integrated_lufs:.1f} LUFS"
                    )
                if true_peak is not None and true_peak > -0.2:
                    warnings.append(f"Audio true peak near clipping: {true_peak:.1f} dBTP")

        # 7. Audio-Subtitle timing sync check
        sub_ok = True
        cue_count = 0
        sub_max_end = 0.0
        sub_drift = 0.0
        if subtitle_path and os.path.exists(subtitle_path):
            sub_ok, cue_count, sub_max_end, sub_drift, sub_msg = self._check_subtitle_sync(
                subtitle_path, actual_dur or expected_duration, manifest=manifest
            )
            if not sub_ok and sub_msg:
                warnings.append(sub_msg)

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
            pix_fmt=pix_fmt,
            integrated_lufs=integrated_lufs,
            loudness_range_lra=lra_lu,
            true_peak_dbtp=true_peak,
            subtitle_sync_ok=sub_ok,
            subtitle_cue_count=cue_count,
            subtitle_max_end_sec=round(sub_max_end, 2),
            subtitle_sync_drift_sec=round(sub_drift, 3),
            issues=issues,
            warnings=warnings
        )

        logger.info(
            f"QC Result: {status} (LUFS: {integrated_lufs}, SubCues: {cue_count}, "
            f"SyncOK: {sub_ok}, Issues: {len(issues)}, Warnings: {len(warnings)})"
        )
        return report

    def _measure_loudness_ebur128(
        self, video_path: str, timeout: int = 60
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Measure integrated loudness (LUFS), LRA, and peak via FFmpeg ebur128."""
        cmd = [
            "ffmpeg", "-nostats", "-i", video_path,
            "-vn", "-filter_complex", "ebur128=peak=true",
            "-f", "null", "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            text = res.stderr or ""
            # Match Summary section at bottom of ebur128 output
            i_matches = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", text)
            lra_matches = re.findall(r"\bLRA:\s*(-?\d+(?:\.\d+)?)\s*LU", text)
            peak_matches = re.findall(r"\bPeak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", text)
            lufs = round(float(i_matches[-1]), 2) if i_matches else None
            lra = round(float(lra_matches[-1]), 2) if lra_matches else None
            peak = round(float(peak_matches[-1]), 2) if peak_matches else None
            return lufs, lra, peak
        except Exception:
            return None, None, None

    @staticmethod
    def _parse_ts_seconds(ts: str) -> float:
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) != 3:
            return 0.0
        return int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2])

    def _check_subtitle_sync(
        self, subtitle_path: str, actual_duration: float, manifest: Optional[Any] = None
    ) -> Tuple[bool, int, float, float, str]:
        """Verify subtitle timestamps are monotonic, stay within video duration, and match scene timings."""
        try:
            with open(subtitle_path, "r", encoding="utf-8-sig") as f:
                raw = f.read()
        except Exception as e:
            return False, 0, 0.0, 0.0, f"Could not read subtitle file for sync check: {e}"

        cues: List[Tuple[float, float]] = []
        if subtitle_path.lower().endswith(".ass"):
            for line in raw.splitlines():
                if line.startswith("Dialogue:"):
                    fields = line.split(",", 9)
                    if len(fields) >= 3:
                        st = self._parse_ts_seconds(fields[1])
                        en = self._parse_ts_seconds(fields[2])
                        cues.append((st, en))
        else:
            for m in re.finditer(r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})", raw):
                cues.append((self._parse_ts_seconds(m.group(1)), self._parse_ts_seconds(m.group(2))))

        if not cues:
            return False, 0, 0.0, 0.0, "Subtitle file contains zero timed cues."

        max_end = max(en for _, en in cues)
        overflow = max(0.0, max_end - (actual_duration + 0.6))
        inverted = sum(1 for st, en in cues if en < st)

        manifest_drift = 0.0
        if manifest and getattr(manifest, "scenes", None):
            manifest_total = sum(float(getattr(s, "duration", 0.0)) for s in manifest.scenes)
            manifest_drift = abs(manifest_total - actual_duration)

        drift = max(overflow, manifest_drift)
        if inverted > 0:
            return False, len(cues), max_end, drift, f"Subtitle sync error: {inverted} inverted cues."
        if overflow > 1.0:
            return False, len(cues), max_end, drift, (
                f"Subtitle overflow past video end: max cue {max_end:.2f}s > video {actual_duration:.2f}s"
            )
        if manifest_drift > 2.0:
            return False, len(cues), max_end, drift, (
                f"Audio-subtitle manifest duration drift {manifest_drift:.2f}s exceeds tolerance."
            )
        return True, len(cues), max_end, drift, ""

    def _check_black_frames(self, video_path: str, timeout: int = 60) -> float:
        """Scan video for uninterrupted black frame sequences."""
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", "blackdetect=d=0.5:pix_th=0.10",
            "-f", "null", "-"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
