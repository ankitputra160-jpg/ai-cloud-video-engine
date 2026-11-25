"""
engine/assets/pixabay.py - Pixabay Stock Media Provider
"""
import json
import logging
import urllib.parse
import urllib.request
import time
from typing import List, Optional
from engine.assets.base import VisualAssetProvider

logger = logging.getLogger("assets.pixabay")

class PixabayProvider(VisualAssetProvider):
    def __init__(self, api_key: Optional[str] = None, timeout: int = 15):
        self.api_key = api_key
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "pixabay"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 8)

    def fetch_video(self, queries: List[str], target_path: str, min_duration: float = 5.0) -> Optional[str]:
        if not self.is_available():
            return None

        for query in queries:
            try:
                q_encoded = urllib.parse.quote(query)
                url = f"https://pixabay.com/api/videos/?key={self.api_key.strip()}&q={q_encoded}&video_type=film&per_page=5"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        hits = data.get("hits", [])
                        for hit in hits:
                            videos = hit.get("videos", {})
                            for res_key in ("large", "medium", "small"):
                                stream = videos.get(res_key, {})
                                if stream.get("url"):
                                    if self._download_file(stream["url"], target_path):
                                        logger.info(f"Pixabay clip downloaded for '{query}'")
                                        return target_path
            except Exception as e:
                logger.warning(f"Pixabay request failed for '{query}': {e}")
        return None

    def _download_file(self, url: str, path: str) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            return True
        except Exception:
            return False
