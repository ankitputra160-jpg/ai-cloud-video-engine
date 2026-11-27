"""
engine/assets/mixkit.py - Keyless, Watermark-Free HD Video B-Roll Provider (Mixkit Free Stock Video)
Retrieves real moving 1080p/720p MP4 stock video clips across documentary, cyber, police,
court, smartphone, family, and city themes without any API key or watermark.
"""
import logging
import os
import re
import subprocess
import time
import urllib.request
from typing import Dict, List, Optional, Set

from engine.assets.base import VisualAssetProvider

logger = logging.getLogger("assets.mixkit")

_MIXKIT_SLUG_KEYWORDS: Dict[str, tuple] = {
    "cyber": ("cyber", "hacker", "hack", "network", "data", "server", "digital", "code", "deepfake", "ai", "neural", "waveform"),
    "smartphone": ("smartphone", "mobile", "whatsapp", "skype", "dial", "1930", "otp", "upi", "app", "screen"),
    "phone": ("phone", "call", "ringing", "caller", "voip", "block", "red end"),
    "laptop": ("laptop", "webcam", "zoom", "desk", "dashboard", "study"),
    "police": ("police", "cbi", "officer", "uniform", "arrest", "badge", "station", "crime", "fraud", "scam"),
    "court": ("court", "judge", "gavel", "law", "legal", "warrant", "justice", "supreme"),
    "prison": ("prison", "jail", "captive", "hostage", "bars", "lockdown"),
    "typing": ("typing", "keyboard", "monitor", "computer", "document", "report"),
    "elderly": ("elderly", "senior", "father", "mother", "retired", "grand", "old"),
    "call-center": ("call center", "headset", "operator", "syndicate", "scam center", "earpiece"),
    "city-night": ("midnight", "evening", "twilight", "street"),
    "city": ("city", "india", "urban", "traffic", "building"),
    "dark": ("dark", "night", "shadow", "dim", "black"),
    "lock": ("lock", "locking", "privacy", "password", "padlock", "pin"),
    "business": ("bank", "rtgs", "account", "escrow", "finance", "rbi", "executive", "manager", "branch", "teller"),
    "money": ("money", "currency", "rupee", "crore", "cash", "atm", "transfer", "fund", "passbook", "fd"),
    "family": ("family", "home", "parents", "living room", "table", "son", "daughter", "sofa"),
    "security": ("security", "shield", "protect", "warning", "alert", "safe"),
    "worried": ("worried", "anxious", "tense", "nervous", "shaky"),
    "scared": ("scared", "shocked", "fear", "panic", "frightened", "threat"),
    "sad": ("stressed", "lonely", "shame", "silence", "upset"),
    "office": ("office", "colleagues", "meeting", "parcel", "warehouse"),
    "news": ("newspaper", "headline", "press", "media", "journalist"),
}


class MixkitVideoProvider(VisualAssetProvider):
    """Fetches real watermark-free 1080p/720p MP4 B-roll clips from Mixkit free stock video."""

    def __init__(self, timeout: int = 20, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps
        self._slug_cache: Dict[str, List[str]] = {}
        self._last_req_ts = 0.0

    @property
    def name(self) -> str:
        return "mixkit_free_video"

    def is_available(self) -> bool:
        return True

    @staticmethod
    def _pick_slugs(queries: List[str]) -> List[str]:
        joined = " ".join(queries).lower()
        scored: List[tuple] = []
        for slug, kws in _MIXKIT_SLUG_KEYWORDS.items():
            hits = sum(1 for k in kws if k in joined)
            if hits > 0:
                scored.append((hits, slug))
        scored.sort(reverse=True)
        slugs = [s for _, s in scored[:3]]
        if not slugs:
            slugs = ["cyber", "smartphone", "office"]
        return slugs

    def _fetch_slug_mp4s(self, slug: str) -> List[str]:
        if slug in self._slug_cache:
            return self._slug_cache[slug]
        elapsed = time.time() - self._last_req_ts
        if elapsed < 0.4:
            time.sleep(0.4 - elapsed)
        self._last_req_ts = time.time()
        url = f"https://mixkit.co/free-stock-video/{slug}/"
        urls: List[str] = []
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    html = resp.read(220_000).decode("utf-8", errors="replace")
                    found = re.findall(r"https://assets\.mixkit\.co/videos/\d+/\d+-(?:720|1080)\.mp4", html)
                    # Derive compact -720.mp4 URLs first (4-9MB full valid MP4 vs 40MB+ 1080p) so moov atom is complete & fast
                    seen_ids: Set[str] = set()
                    for m_url in sorted(found, key=lambda u: (0 if "-720.mp4" in u else 1)):
                        vid_id = m_url.rsplit("/", 1)[-1].split("-")[0]
                        compact_url = re.sub(r"-1080\.mp4$", "-720.mp4", m_url)
                        if vid_id not in seen_ids:
                            seen_ids.add(vid_id)
                            urls.append(compact_url)
        except Exception as e:
            logger.debug(f"Mixkit slug fetch skipped ({slug}): {e}")
        self._slug_cache[slug] = urls
        return urls

    def fetch_video(
        self,
        queries: List[str],
        target_path: str,
        min_duration: float = 5.0,
        used_urls: Optional[Set[str]] = None,
    ) -> Optional[str]:
        used = used_urls if used_urls is not None else set()
        dur = max(1.5, float(min_duration))
        slugs = self._pick_slugs(queries)

        for slug in slugs:
            candidates = self._fetch_slug_mp4s(slug)
            for vid_url in candidates:
                if vid_url in used:
                    continue
                raw_dl = target_path + ".mixkit_raw.mp4"
                try:
                    req = urllib.request.Request(
                        vid_url,
                        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0"},
                    )
                    with urllib.request.urlopen(req, timeout=max(25, self.timeout)) as resp, open(raw_dl, "wb") as f:
                        if resp.status != 200:
                            continue
                        # Download up to 18MB (more than enough for 3-10s 1080p clip!)
                        downloaded = 0
                        while downloaded < 18 * 1024 * 1024:
                            chunk = resp.read(131072)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                    if os.path.exists(raw_dl) and os.path.getsize(raw_dl) > 120_000:
                        # Scale & crop cleanly to 16:9 full-bleed moving video clip (never letterbox!)
                        vf = (
                            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                            f"crop={self.width}:{self.height},"
                            f"fps={self.fps},setsar=1,format=yuv420p"
                        )
                        cmd = [
                            "ffmpeg", "-y", "-loglevel", "error",
                            "-stream_loop", "-1", "-i", raw_dl,
                            "-vf", vf,
                            "-t", f"{dur:.3f}",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                            "-pix_fmt", "yuv420p", "-color_range", "tv", "-an",
                            target_path,
                        ]
                        res = subprocess.run(cmd, capture_output=True)
                        if os.path.exists(raw_dl):
                            os.remove(raw_dl)
                        if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 10_000:
                            used.add(vid_url)
                            logger.info(f"Mixkit HD B-roll video ({slug}): {vid_url}")
                            return target_path
                except Exception as e:
                    logger.debug(f"Mixkit video download skipped ({vid_url}): {e}")
                    if os.path.exists(raw_dl):
                        os.remove(raw_dl)
        return None
