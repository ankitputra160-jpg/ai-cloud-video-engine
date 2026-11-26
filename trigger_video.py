#!/usr/bin/env python3
"""
trigger_video.py - Hardened, Mobile-First Cloud Trigger Client
Dispatches AI Documentary Video Generation to GitHub Actions and downloads the finished output safely.
"""

import subprocess
import sys
import time
import os
import json
import argparse
import shlex
from typing import Optional, Tuple, Dict, Any

REPO = "ankitputra160-jpg/ai-cloud-video-engine"
WORKFLOW = "generate_documentary.yml"
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/storage/downloads/ai_documentaries")

def safe_run_command(cmd_args: list, check: bool = True) -> Tuple[int, str, str]:
    """Execute command safely without shell=True to eliminate command injection vulnerabilities."""
    try:
        proc = subprocess.run(cmd_args, capture_output=True, text=True, check=False)
        if check and proc.returncode != 0:
            print(f"❌ Execution error (code {proc.returncode}): {proc.stderr.strip()}")
            sys.exit(proc.returncode)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        print(f"❌ Command not found: {cmd_args[0]}. Ensure GitHub CLI ('gh') is installed.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error executing {cmd_args[0]}: {e}")
        sys.exit(1)

def trigger_workflow(
    topic: str,
    language: str,
    duration: int,
    resolution: str,
    style: str,
    subtitle_style: str = "ass_karaoke",
    voice_engine: str = "auto",
    storyboard_file: Optional[str] = None,
) -> None:
    print("\n" + "="*60)
    print("🚀 DISPATCHING AI DOCUMENTARY PIPELINE TO CLOUD")
    print("="*60)
    print(f"   📋 Topic: {topic}")
    print(f"   🌐 Language: {language}")
    print(f"   ⏱️ Target Duration: {duration}s")
    print(f"   🖥️ Resolution: {resolution}")
    print(f"   🎨 Style: {style} | Subtitles: {subtitle_style} | Voice: {voice_engine}")

    cmd = [
        "gh", "workflow", "run", WORKFLOW,
        "--repo", REPO,
        "-f", f"topic={topic}",
        "-f", f"language={language}",
        "-f", f"duration={str(duration)}",
        "-f", f"resolution={resolution}",
        "-f", f"style={style}",
        "-f", f"subtitle_style={subtitle_style}",
        "-f", f"voice_engine={voice_engine}",
    ]
    if storyboard_file:
        cmd.extend(["-f", f"storyboard_file={storyboard_file}"])
    safe_run_command(cmd, check=True)
    print("✅ Cloud workflow successfully triggered!")
    time.sleep(6)  # Allow GitHub Actions API to register the job

def get_latest_run_id() -> Tuple[int, str, str]:
    cmd = [
        "gh", "run", "list",
        "--repo", REPO,
        "--workflow", WORKFLOW,
        "--limit", "1",
        "--json", "databaseId,status,conclusion"
    ]
    _, stdout, _ = safe_run_command(cmd, check=True)
    try:
        runs = json.loads(stdout)
        if not runs:
            print("❌ No active workflow runs found on GitHub.")
            sys.exit(1)
        return int(runs[0]["databaseId"]), str(runs[0].get("status", "")), str(runs[0].get("conclusion", ""))
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"❌ Failed to parse workflow runs: {e}")
        sys.exit(1)

def wait_for_completion(run_id: int, max_wait_seconds: int = 5400) -> bool:
    """Poll GitHub Actions run status with progressive backoff and spinner."""
    print(f"\n⏳ Monitoring Cloud Worker Job #{run_id} (Timeout: {max_wait_seconds}s)...")
    start_time = time.time()
    poll_interval = 10

    while time.time() - start_time < max_wait_seconds:
        cmd = [
            "gh", "run", "view", str(run_id),
            "--repo", REPO,
            "--json", "status,conclusion,jobs"
        ]
        code, stdout, _ = safe_run_command(cmd, check=False)
        if code == 0:
            try:
                data = json.loads(stdout)
                status = data.get("status")
                conclusion = data.get("conclusion")

                elapsed = int(time.time() - start_time)
                print(f"   ⚙️ Status: [{status.upper()}] | Elapsed: {elapsed}s", end="\r", flush=True)

                if status == "completed":
                    print("\n")
                    if conclusion == "success":
                        print("🎉 Cloud workflow execution completed successfully!")
                        return True
                    else:
                        print(f"❌ Cloud workflow failed with conclusion: '{conclusion}'")
                        print(f"🔗 View failure logs: https://github.com/{REPO}/actions/runs/{run_id}")
                        return False
            except json.JSONDecodeError:
                pass

        time.sleep(poll_interval)

    print(f"\n⏰ Job monitoring timed out after {max_wait_seconds} seconds.")
    return False

def download_video_artifact(run_id: int, destination_dir: str) -> Optional[str]:
    """Download the final documentary artifact and verify file size."""
    os.makedirs(destination_dir, exist_ok=True)
    print(f"📥 Downloading documentary video to: {destination_dir}...")

    cmd = [
        "gh", "run", "download", str(run_id),
        "--repo", REPO,
        "--dir", destination_dir
    ]
    code, _, stderr = safe_run_command(cmd, check=False)
    if code != 0:
        print(f"❌ Failed to download artifact: {stderr}")
        return None

    # Locate generated MP4 in destination
    for root, _, files in os.walk(destination_dir):
        for f in files:
            if f.endswith(".mp4"):
                full_path = os.path.join(root, f)
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                print("\n" + "="*60)
                print("🏆 DOCUMENTARY DELIVERED TO MOBILE DEVICE")
                print("="*60)
                print(f"   📁 Local Path: {full_path}")
                print(f"   📦 File Size: {size_mb:.2f} MB")
                print(f"   ▶️ Play Video: file://{full_path}\n")
                return full_path

    print("⚠️ Artifact downloaded but no .mp4 video was found in archive.")
    return None

def main():
    parser = argparse.ArgumentParser(description="Trigger AI Documentary Generation on GitHub Cloud")
    parser.add_argument("--topic", default="The History of Ancient Indian Astronomy", help="Documentary subject")
    parser.add_argument("--language", default="en", choices=["en", "hi"], help="Narration language (en / hi)")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds (10 to 1500 / 25 min)")
    parser.add_argument("--resolution", default="1080p", choices=["1080p", "4k", "720p"], help="Video resolution")
    parser.add_argument("--style", default="Documentary", help="Style (Documentary, 2D Animation, Vox Explainer, Historical, Scientific)")
    parser.add_argument("--subtitle-style", default="ass_karaoke", choices=["ass_karaoke", "pill_box", "srt_classic"], help="Subtitle style preset")
    parser.add_argument("--voice-engine", default="auto", choices=["auto", "piper", "edge"], help="Open-source Piper or Edge Neural voice")
    parser.add_argument("--storyboard-file", default=None, help="Optional curated storyboard JSON in repo")
    parser.add_argument("--output-dir", default=DEFAULT_DOWNLOAD_DIR, help="Local directory to save output")
    args = parser.parse_args()

    # Pre-flight check: gh authenticated
    code, _, _ = safe_run_command(["gh", "auth", "status"], check=False)
    if code != 0:
        print("❌ GitHub CLI is not authenticated. Run 'gh auth login' first.")
        sys.exit(1)

    # 1. Trigger the job
    trigger_workflow(
        topic=args.topic,
        language=args.language,
        duration=args.duration,
        resolution=args.resolution,
        style=args.style,
        subtitle_style=args.subtitle_style,
        voice_engine=args.voice_engine,
        storyboard_file=args.storyboard_file,
    )

    # 2. Get Run ID
    run_id, _, _ = get_latest_run_id()
    print(f"📌 Cloud Run ID: {run_id}")
    print(f"🔗 Track live online: https://github.com/{REPO}/actions/runs/{run_id}")

    # 3. Wait for cloud completion
    if wait_for_completion(run_id):
        # 4. Download final artifact
        download_video_artifact(run_id, args.output_dir)
    else:
        print(f"Inspect cloud job logs at: https://github.com/{REPO}/actions/runs/{run_id}")

if __name__ == "__main__":
    main()
