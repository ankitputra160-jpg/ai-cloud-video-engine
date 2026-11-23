"""
Cloud Video Clip Downloader
Downloads real 4K stock video clips from Pexels API based on topic
"""
import os
import sys
import requests
import json

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
OUTPUT_DIR = "clips"

TOPIC_KEYWORDS = {
    "abandoned bus": ["rusty bus abandoned", "old school bus junkyard", "bus restoration", "metal wrench bolt", "pressure washer metal", "angle grinder sparks", "wood workshop carpentry", "luxury interior LED"],
    "car": ["rusty car restoration", "car junkyard abandoned", "mechanic wrench", "car welding sparks", "auto body repair", "car painting spray", "luxury car interior", "car detailing"],
    "mini home": ["tiny house build", "cabin construction wood", "off grid solar panels", "small home interior", "wood framing house", "tiny home kitchen", "minimalist interior design", "log cabin forest"],
    "default": ["metal restoration", "workshop tools", "crafting satisfying", "carpentry wood", "industrial machinery", "spray painting", "LED light interior", "luxury reveal"]
}

def get_keywords(topic):
    topic_lower = topic.lower()
    for key in TOPIC_KEYWORDS:
        if key in topic_lower:
            return TOPIC_KEYWORDS[key]
    return TOPIC_KEYWORDS["default"]

def download_video(url, path):
    r = requests.get(url, stream=True)
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return os.path.getsize(path)

def search_pexels(query, per_page=1):
    if not PEXELS_API_KEY:
        return None
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": per_page, "orientation": "landscape", "size": "large"}
    r = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params)
    if r.status_code == 200:
        data = r.json()
        if data.get("videos"):
            # Get the best quality HD file
            video = data["videos"][0]
            files = sorted(video.get("video_files", []), key=lambda x: x.get("width", 0), reverse=True)
            for f in files:
                if f.get("width", 0) >= 1280:
                    return f["link"]
    return None

def generate_fallback_clip(output_path, scene_num, duration=6):
    """Generate a colored test clip if no API key"""
    colors = ["red", "blue", "green", "orange", "purple", "cyan", "yellow", "white"]
    color = colors[scene_num % len(colors)]
    os.system(f'ffmpeg -y -f lavfi -i "color=c={color}:size=1920x1080:duration={duration}" '
              f'-f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=44100" '
              f'-c:v libx264 -preset ultrafast -c:a aac -t {duration} {output_path}')

def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "abandoned bus to luxury mini home"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    keywords = get_keywords(topic)
    
    # Number of clips needed (6 seconds each)
    num_clips = max(8, duration // 6)
    clips_downloaded = []
    
    print(f"🔍 Searching for '{topic}' video clips...")
    print(f"📊 Need {num_clips} clips of 6 seconds each")
    
    for i, keyword in enumerate(keywords[:num_clips]):
        output_path = f"{OUTPUT_DIR}/clip_{i:02d}.mp4"
        
        if PEXELS_API_KEY:
            print(f"[{i+1}/{num_clips}] Searching: '{keyword}'...")
            video_url = search_pexels(keyword)
            if video_url:
                size = download_video(video_url, f"{OUTPUT_DIR}/raw_{i:02d}.mp4")
                # Trim to 6 seconds and convert to 1080p
                os.system(f'ffmpeg -y -i {OUTPUT_DIR}/raw_{i:02d}.mp4 '
                          f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" '
                          f'-c:v libx264 -preset ultrafast -crf 23 -t 6 -an {output_path}')
                clips_downloaded.append(output_path)
                print(f"✅ Downloaded: {os.path.getsize(output_path)//1024}KB")
                continue
        
        # Fallback: generate placeholder clip
        print(f"[{i+1}/{num_clips}] Generating placeholder clip (no API key)...")
        generate_fallback_clip(output_path, i)
        clips_downloaded.append(output_path)
    
    # Save clip manifest
    with open(f"{OUTPUT_DIR}/manifest.json", "w") as f:
        json.dump({"topic": topic, "clips": clips_downloaded, "count": len(clips_downloaded)}, f)
    
    print(f"\n✅ Ready: {len(clips_downloaded)} clips in '{OUTPUT_DIR}/'")

if __name__ == "__main__":
    main()
