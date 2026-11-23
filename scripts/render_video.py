#!/usr/bin/env python3
"""
render_video.py - Final video assembly script for AI Cloud Video Engine
Concatenates clips, overlays ASMR SFX per scene, mixes soft BGM, outputs final_video.mp4
"""

import os
import sys
import json
import subprocess
import argparse
import glob

def run_ffmpeg(cmd, label=""):
    print(f"🎬 FFmpeg: {label}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr[-500:]}")
        return False
    print(f"✅ Done: {label}")
    return True

def get_duration(filepath):
    """Get duration of a media file in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 6.0

def create_colored_placeholder(output_path, color_hex, duration=6, width=1920, height=1080):
    """Create a colored placeholder video if clip is missing."""
    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color_hex}:size={width}x{height}:rate=25",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)
    print(f"🎨 Created placeholder: {output_path}")

def normalize_clip(input_path, output_path, duration=6):
    """Normalize a clip to 1920x1080, 25fps, H264."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-r", "25",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",
        output_path
    ]
    return run_ffmpeg(cmd, f"Normalize {os.path.basename(input_path)}")

def mix_audio_for_clip(video_path, sfx_path, bgm_path, output_path, sfx_vol=1.0, bgm_vol=0.18):
    """Mix SFX + BGM and mux with video."""
    duration = get_duration(video_path)

    # Build filter for audio mixing
    audio_filter = (
        f"[1:a]volume={sfx_vol}[sfx];"
        f"[2:a]volume={bgm_vol},aloop=loop=-1:size=2e+09[bgm];"
        f"[sfx][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", sfx_path,
        "-i", bgm_path,
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        output_path
    ]
    return run_ffmpeg(cmd, f"Mix audio for {os.path.basename(video_path)}")

def concat_videos(clip_list, output_path):
    """Concatenate multiple video files into one."""
    # Write concat list
    list_path = "/tmp/concat_list.txt"
    with open(list_path, "w") as f:
        for clip in clip_list:
            f.write(f"file '{clip}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]
    return run_ffmpeg(cmd, "Final concat")

def main():
    parser = argparse.ArgumentParser(description="Render AI crafting video")
    parser.add_argument("--topic", default="abandoned bus to luxury mini home", help="Video topic")
    parser.add_argument("--style", default="ASMR Crafting", help="Video style")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds")
    parser.add_argument("--clips-dir", default="clips", help="Directory with downloaded clips")
    parser.add_argument("--audio-dir", default="audio", help="Directory with audio files")
    parser.add_argument("--output", default="output/final_video.mp4", help="Output file path")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"🎬 AI Cloud Video Engine - Render Script")
    print(f"📋 Topic: {args.topic}")
    print(f"🎵 Style: {args.style}")
    print(f"⏱️  Target Duration: {args.duration}s")
    print(f"{'='*60}\n")

    # Setup directories
    os.makedirs("output", exist_ok=True)
    os.makedirs("/tmp/rendered_clips", exist_ok=True)

    # Scene colors (fallback placeholders)
    scene_colors = [
        "#1a1a2e",  # Scene 1: Dark abandoned bus
        "#2d1b00",  # Scene 2: Rust brown
        "#003366",  # Scene 3: Water blue
        "#4a4a4a",  # Scene 4: Metal grey
        "#2d4a1e",  # Scene 5: Wood green
        "#1a3a4a",  # Scene 6: Modern interior
        "#FF6B35",  # Scene 7: Paint orange
        "#c8a84b",  # Scene 8: Luxury gold
    ]

    # Find clips
    manifest_path = os.path.join(args.clips_dir, "manifest.json")
    clips = []

    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f"📋 Manifest loaded: {len(manifest)} scenes")
        for item in manifest:
            clips.append(item.get("local_path", ""))
    else:
        # Auto-discover clips
        for ext in ["*.mp4", "*.mov", "*.webm"]:
            found = sorted(glob.glob(os.path.join(args.clips_dir, ext)))
            if found:
                clips = found
                break
        print(f"🔍 Auto-discovered {len(clips)} clips")

    # Determine scene count
    scene_count = max(len(clips), 8)
    clip_duration = max(6, args.duration // scene_count)

    print(f"\n📽️  Processing {scene_count} scenes ({clip_duration}s each)...\n")

    # SFX files
    sfx_dir = os.path.join(args.audio_dir, "sfx")
    sfx_files = sorted(glob.glob(os.path.join(sfx_dir, "*.wav")))
    if not sfx_files:
        sfx_files = sorted(glob.glob(os.path.join(sfx_dir, "*.mp3")))

    # BGM file
    bgm_path = os.path.join(args.audio_dir, "bgm", "bgm_chill_loop.wav")
    if not os.path.exists(bgm_path):
        bgm_files = glob.glob(os.path.join(args.audio_dir, "bgm", "*"))
        bgm_path = bgm_files[0] if bgm_files else None

    print(f"🎵 SFX files found: {len(sfx_files)}")
    print(f"🎼 BGM: {bgm_path or 'None (audio-only mode)'}\n")

    # Process each scene
    final_clips = []

    for i in range(scene_count):
        scene_num = i + 1
        print(f"--- Scene {scene_num}/{scene_count} ---")

        raw_clip = "/tmp/rendered_clips/raw_{:02d}.mp4".format(i)
        norm_clip = "/tmp/rendered_clips/norm_{:02d}.mp4".format(i)
        final_clip = "/tmp/rendered_clips/final_{:02d}.mp4".format(i)

        # Get source clip
        source_clip = clips[i] if i < len(clips) else None

        if source_clip and os.path.exists(source_clip):
            # Normalize real clip
            normalize_clip(source_clip, norm_clip, clip_duration)
        else:
            # Create colored placeholder
            color = scene_colors[i % len(scene_colors)]
            create_colored_placeholder(norm_clip, color, clip_duration)

        # Get SFX for this scene
        sfx_path = sfx_files[i % len(sfx_files)] if sfx_files else None

        if sfx_path and bgm_path and os.path.exists(sfx_path):
            # Mix audio with video
            mix_audio_for_clip(norm_clip, sfx_path, bgm_path, final_clip)
        elif bgm_path:
            # BGM only
            audio_filter = f"[1:a]volume=0.18,aloop=loop=-1:size=2e+09[aout]"
            cmd = [
                "ffmpeg", "-y",
                "-i", norm_clip,
                "-i", bgm_path,
                "-filter_complex", audio_filter,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", str(clip_duration),
                final_clip
            ]
            run_ffmpeg(cmd, f"BGM-only scene {scene_num}")
        else:
            # No audio — just use normalized clip
            final_clip = norm_clip

        if os.path.exists(final_clip):
            final_clips.append(final_clip)
            size = os.path.getsize(final_clip) / 1024
            print(f"✅ Scene {scene_num} ready ({size:.0f} KB)\n")
        else:
            print(f"⚠️  Scene {scene_num} failed, skipping\n")

    # Final concat
    print(f"\n{'='*60}")
    print(f"🔗 Concatenating {len(final_clips)} scenes...")

    if final_clips:
        success = concat_videos(final_clips, args.output)
        if success and os.path.exists(args.output):
            size_mb = os.path.getsize(args.output) / (1024 * 1024)
            duration_actual = get_duration(args.output)
            print(f"\n{'='*60}")
            print(f"🎉 VIDEO RENDER COMPLETE!")
            print(f"📁 Output: {args.output}")
            print(f"📦 Size: {size_mb:.1f} MB")
            print(f"⏱️  Duration: {duration_actual:.1f}s")
            print(f"🎬 Topic: {args.topic}")
            print(f"{'='*60}\n")
        else:
            print("❌ Final concat failed!")
            sys.exit(1)
    else:
        print("❌ No clips to concat!")
        sys.exit(1)

if __name__ == "__main__":
    main()
