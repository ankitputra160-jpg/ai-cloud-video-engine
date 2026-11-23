#!/usr/bin/env python3
"""
trigger_video.py - AntiGem Phone Trigger Script
Triggers GitHub Actions video generation and downloads the result to your phone.

Usage:
    python3 trigger_video.py --topic "abandoned bus restoration" --style "ASMR Crafting" --duration 180
"""

import subprocess
import sys
import time
import os
import json
import argparse

REPO = "ankitputra160-jpg/ai-cloud-video-engine"
WORKFLOW = "generate_video.yml"
DOWNLOAD_DIR = os.path.expanduser("~/storage/downloads/ai_videos")

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def trigger_workflow(topic, style, duration):
    print(f"🚀 Triggering GitHub Actions workflow...")
    print(f"   📋 Topic: {topic}")
    print(f"   🎨 Style: {style}")
    print(f"   ⏱️  Duration: {duration}s")

    cmd = (
        f'gh workflow run {WORKFLOW} --repo {REPO} '
        f'-f topic="{topic}" '
        f'-f style="{style}" '
        f'-f duration="{duration}"'
    )
    run(cmd)
    print("✅ Workflow triggered!\n")
    time.sleep(5)  # Wait for GitHub to register the run

def get_latest_run_id():
    out = run(f'gh run list --repo {REPO} --workflow {WORKFLOW} --limit 1 --json databaseId,status,conclusion')
    runs = json.loads(out)
    if not runs:
        print("❌ No runs found!")
        sys.exit(1)
    return runs[0]["databaseId"], runs[0].get("status"), runs[0].get("conclusion")

def wait_for_completion(run_id, max_wait=900):
    """Poll until workflow completes (max 15 minutes)."""
    print(f"⏳ Waiting for run #{run_id} to complete...")
    start = time.time()
    dots = 0

    while time.time() - start < max_wait:
        out = run(f'gh run view {run_id} --repo {REPO} --json status,conclusion')
        data = json.loads(out)
        status = data.get("status")
        conclusion = data.get("conclusion")

        if status == "completed":
            if conclusion == "success":
                print(f"\n✅ Workflow completed successfully!")
                return True
            else:
                print(f"\n❌ Workflow failed! Conclusion: {conclusion}")
                print(f"   View logs: https://github.com/{REPO}/actions/runs/{run_id}")
                return False

        dots += 1
        print(f"   {'.' * (dots % 20)} [{status}] {int(time.time()-start)}s elapsed", end="\r")
        time.sleep(15)

    print(f"\n⏰ Timeout after {max_wait}s!")
    return False

def download_artifact(run_id, output_dir):
    """Download the video artifact from GitHub Actions."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n📥 Downloading video artifact...")

    cmd = f'gh run download {run_id} --repo {REPO} --dir "{output_dir}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        # Find the downloaded video
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if f.endswith(".mp4"):
                    full_path = os.path.join(root, f)
                    size_mb = os.path.getsize(full_path) / (1024*1024)
                    print(f"\n🎉 VIDEO DOWNLOADED!")
                    print(f"   📁 Path: {full_path}")
                    print(f"   📦 Size: {size_mb:.1f} MB")
                    print(f"\n   Open in gallery: file://{full_path}\n")
                    return full_path
        print("⚠️  Artifact downloaded but no .mp4 found")
    else:
        print(f"❌ Download failed: {result.stderr}")

    return None

def main():
    parser = argparse.ArgumentParser(description="Trigger AI video generation on GitHub Actions")
    parser.add_argument("--topic", default="abandoned bus to luxury mini home",
                       help="Video topic (e.g. 'rusty car restoration')")
    parser.add_argument("--style", default="ASMR Crafting",
                       choices=["ASMR Crafting", "Documentary", "Satisfying Tools"],
                       help="Video style")
    parser.add_argument("--duration", type=int, default=120,
                       help="Duration in seconds (60-300)")
    parser.add_argument("--output-dir", default=DOWNLOAD_DIR,
                       help="Where to save the downloaded video")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("🎬 AI Cloud Video Engine - Phone Trigger")
    print("="*60 + "\n")

    # Check gh is available
    run("gh --version", check=True)

    # Trigger the workflow
    trigger_workflow(args.topic, args.style, args.duration)

    # Get run ID
    run_id, status, conclusion = get_latest_run_id()
    print(f"📌 Run ID: {run_id}")
    print(f"   View: https://github.com/{REPO}/actions/runs/{run_id}\n")

    # Wait for completion
    if wait_for_completion(run_id):
        # Download result
        video_path = download_artifact(run_id, args.output_dir)
        if video_path:
            print("✅ All done! Video is on your phone.")
        else:
            print(f"⚠️  Download manually: https://github.com/{REPO}/actions/runs/{run_id}")
    else:
        print(f"🔗 Check workflow: https://github.com/{REPO}/actions/runs/{run_id}")

if __name__ == "__main__":
    main()
