"""
engine/assets/wikimedia.py - Wikimedia Commons Open Media Provider
Accesses public domain and Creative Commons video and high-resolution media without requiring API keys.
"""
import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional
from engine.assets.base import VisualAssetProvider

logger = logging.getLogger("assets.wikimedia")

class WikimediaCommonsProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "wikimedia_commons"

    def is_available(self) -> bool:
        # Wikimedia Commons public API requires no private key
        return True

    def fetch_video(self, queries: List[str], target_path: str, min_duration: float = 5.0) -> Optional[str]:
        for query in queries:
            try:
                # Search for video files on Commons
                encoded_q = urllib.parse.quote(f"{query} filetype:video")
                url = (
                    f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                    f"&gsrsearch={encoded_q}&gsrnamespace=6&gsrlimit=5&prop=imageinfo"
                    f"&iiprop=url|mime|size&format=json"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.0 (open media research)"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        pages = data.get("query", {}).get("pages", {})
                        for page in pages.values():
                            imageinfo = page.get("imageinfo", [])
                            if imageinfo:
                                file_url = imageinfo[0].get("url")
                                mime = imageinfo[0].get("mime", "")
                                if file_url and ("video" in mime or file_url.endswith((".webm", ".mp4", ".ogv"))):
                                    if self._download_file(file_url, target_path):
                                        logger.info(f"Wikimedia video retrieved: {file_url}")
                                        return target_path
            except Exception as e:
                logger.debug(f"Wikimedia lookup note for '{query}': {e}")
        return None

    def _download_file(self, url: str, path: str) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            return True
        except Exception:
            return False
