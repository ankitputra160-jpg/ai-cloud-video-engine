# 🎬 AI Cloud Video Engine

> Fully automated, cloud-based AI video generation pipeline — rendered on GitHub Actions, delivered to your phone.

## 🚀 Features

- **Real 4K stock footage** from Pexels API (no static images)
- **ASMR sound effects** synced per scene (wrench, grinder, water spray, etc.)
- **Soft Lo-Fi BGM** at 18% volume underneath SFX
- **16:9, 1920×1080**, 3–5 minutes output
- **Zero mobile data** cost for rendering — GitHub cloud does all the work
- **Private repo** — your content stays yours

## ⚙️ Setup

### 1. Add Pexels API Key (Free)

1. Go to [pexels.com/api](https://www.pexels.com/api/) → Sign up → Copy your API key
2. Go to: `https://github.com/ankitputra160-jpg/ai-cloud-video-engine/settings/secrets/actions`
3. Click **New repository secret**
4. Name: `PEXELS_API_KEY`, Value: your key → **Add secret**

### 2. Trigger a Video (via AntiGem app)

Run the trigger script from your phone:
```bash
python3 trigger_video.py --topic "abandoned bus to luxury mini home" --style "ASMR Crafting" --duration 180
```

Or manually via GitHub Actions:
- Go to: Actions → AI Cloud Video Generator → Run workflow
- Fill in topic, style, duration → **Run workflow**

### 3. Download Output

After ~5-10 minutes, the video artifact appears in the GitHub Actions run.
The trigger script auto-downloads it to your phone.

## 📂 Project Structure

```
ai-cloud-video-engine/
├── .github/workflows/
│   └── generate_video.yml    # GitHub Actions pipeline
├── scripts/
│   ├── download_clips.py     # Fetches 4K clips from Pexels
│   ├── generate_audio.py     # Synthesizes ASMR SFX + BGM
│   └── render_video.py       # Assembles final video with FFmpeg
├── output/                   # Final video uploaded as artifact
└── README.md
```

## 🎯 Video Topics You Can Try

| Topic | Style |
|-------|-------|
| `abandoned bus to luxury mini home` | ASMR Crafting |
| `rusty car full restoration` | ASMR Crafting |
| `tiny home build from scratch` | Documentary |
| `old motorcycle restoration` | Satisfying Tools |

## 🔧 Requirements (all handled automatically by GitHub Actions)

- FFmpeg (latest)
- Python 3.x
- requests, Pillow
- Pexels API key (free tier: 200 req/hour)

## 📊 GitHub Actions Free Tier

- ✅ 2000 minutes/month for private repos
- ✅ Ubuntu runner: 7GB RAM, 30GB SSD, ~1Gbps internet
- ✅ Artifact storage: up to 500MB per video

---

Made with ❤️ using AntiGem AI + GitHub Actions
