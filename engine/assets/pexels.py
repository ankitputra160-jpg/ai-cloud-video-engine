"""
engine/assets/pexels.py - Pexels 4K/HD Stock Video Provider
"""
import json
import logging
import urllib.parse
import urllib.request
import time
from typing import List, Optional
from engine.assets.base import VisualAssetProvider

logger = logging.getLogger("assets.pexels")

class PexelsProvider(VisualAssetProvider):
    def __init__(self, api_key: Optional[str] = None, timeout: int = 15, max_retries: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return "pexels"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 10)

    def fetch_video(self, queries: List[str], target_path: str, min_duration: float = 5.0) -> Optional[str]:
        if not self.is_available():
            logger.debug("Pexels provider skipped: no API key")
            return None

        headers = {"Authorization": self.api_key.strip()}

        for query in queries:
            for attempt in range(self.max_retries):
                try:
                    q_encoded = urllib.parse.quote(query)
                    url = f"https://api.pexels.com/videos/search?query={q_encoded}&per_page=5&orientation=landscape&size=large"
                    req = urllib.request.Request(url, headers=headers)
                    
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            videos = data.get("videos", [])
                            if not videos:
                                break
                            
                            # Select highest quality stream >= 1080p
                            download_url = self._select_best_stream(videos, min_duration)
                            if download_url:
                                if self._download_file(download_url, target_path):
                                    logger.info(f"Successfully downloaded Pexels video for query '{query}'")
                                    return target_path
                    break
                except Exception as e:
                    logger.warning(f"Pexels search attempt {attempt+1} failed for '{query}': {e}")
                    time.sleep(1.0 * (attempt + 1))
        return None

    def _select_best_stream(self, videos: list, min_duration: float) -> Optional[str]:
        for vid in videos:
            if vid.get("duration", 0) >= min_duration:
                files = sorted(vid.get("video_files", []), key=lambda x: x.get("width", 0), reverse=True)
                for f in files:
                    if f.get("width", 0) >= 1280 and f.get("link"):
                        return f["link"]
        # Fallback to any valid link
        if videos and videos[0].get("video_files"):
            return videos[0]["video_files"][0].get("link")
        return None

    def _download_file(self, url: str, path: str) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Download failed from {url}: {e}")
            return False
