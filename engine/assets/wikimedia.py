"""
engine/assets/wikimedia.py - Rate-Limited Wikimedia Commons & Wikipedia PageImages Provider
Retrieves real archival photos & videos with automatic 429 backoff, caching, and Ken Burns motion.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Set

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.wikimedia")


class WikimediaCommonsProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 15, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps
        self._last_req_ts = 0.0
        self._query_cache: Dict[str, List[Dict[str, str]]] = {}

    @property
    def name(self) -> str:
        return "wikimedia_commons"

    def is_available(self) -> bool:
        return True

    def _throttled_get_json(self, url: str) -> Optional[dict]:
        """Execute polite rate-limited GET with 429 exponential backoff."""
        elapsed = time.time() - self._last_req_ts
        if elapsed < 0.35:
            time.sleep(0.35 - elapsed)

        for attempt in range(3):
            self._last_req_ts = time.time()
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "AIDocEngine/2.6 (educational documentary; contact@aidocengine.invalid)"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait_s = 2.0 * (attempt + 1)
                    logger.debug(f"Wikimedia 429 rate-limit, backing off {wait_s}s...")
                    time.sleep(wait_s)
                    continue
                logger.debug(f"Wikimedia HTTP error {e.code} for {url}")
                return None
            except Exception as e:
                logger.debug(f"Wikimedia request note: {e}")
                return None
        return None

    def fetch_direct_url_as_video(
        self,
        media_url: str,
        target_path: str,
        duration: float,
        camera: str = "push_in",
        date_badge: str = "",
    ) -> Optional[str]:
        """Download an explicit curated photo or video URL and animate/normalize cleanly."""
        if not media_url:
            return None
        lower = media_url.lower()
        if lower.endswith((".mp4", ".webm", ".ogv")):
            if self._download_file(media_url, target_path, min_bytes=10000):
                return target_path
            return None

        ext = ".png" if ".png" in lower else ".jpg"
        tmp_img = target_path + f".direct{ext}"
        if self._download_file(media_url, tmp_img, min_bytes=10000):
            anim = animate_image_to_video(
                tmp_img,
                target_path,
                duration=duration,
                width=self.width,
                height=self.height,
                fps=self.fps,
                camera=camera,
                date_badge=date_badge,
            )
            if os.path.exists(tmp_img):
                os.remove(tmp_img)
            if anim:
                return target_path
        elif os.path.exists(tmp_img):
            os.remove(tmp_img)
        return None

    def fetch_video(
        self,
        queries: List[str],
        target_path: str,
        min_duration: float = 5.0,
        used_urls: Optional[Set[str]] = None,
        camera: str = "push_in",
        date_badge: str = "",
        prefer_images: bool = False,
    ) -> Optional[str]:
        used = used_urls if used_urls is not None else set()

        if not prefer_images:
            res = self._search_media(queries, target_path, "video", used, min_duration, camera, date_badge)
            if res:
                return res

        # Search high-res historical & archival photos on Commons + Wikipedia pageimages
        res = self._search_media(queries, target_path, "bitmap", used, min_duration, camera, date_badge)
        if res:
            return res

        res = self._search_wiki_pageimages(queries, target_path, used, min_duration, camera, date_badge)
        if res:
            return res

        if prefer_images:
            return self._search_media(queries, target_path, "video", used, min_duration, camera, date_badge)
        return None

    def _search_wiki_pageimages(
        self,
        queries: List[str],
        target_path: str,
        used: Set[str],
        duration: float,
        camera: str,
        date_badge: str,
    ) -> Optional[str]:
        """Resolve authentic entity/topic photos via Wikipedia pageimages API."""
        for query in queries[:2]:
            enc = urllib.parse.quote(query)
            url = (
                f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
                f"&gsrsearch={enc}&gsrlimit=4&prop=pageimages&piprop=original|thumbnail&pithumbsize=1400&format=json"
            )
            data = self._throttled_get_json(url)
            if not data:
                continue
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                img_url = page.get("original", {}).get("source") or page.get("thumbnail", {}).get("source")
                if not img_url or img_url in used or img_url.lower().endswith(".svg"):
                    continue
                if self.fetch_direct_url_as_video(img_url, target_path, duration, camera, date_badge):
                    used.add(img_url)
                    logger.info(f"Wikipedia pageimage animated: {img_url}")
                    return target_path
        return None

    def _search_media(
        self,
        queries: List[str],
        target_path: str,
        filetype: str,
        used: Set[str],
        duration: float,
        camera: str,
        date_badge: str,
    ) -> Optional[str]:
        for query in queries:
            cache_key = f"{filetype}:{query}"
            candidates = self._query_cache.get(cache_key)

            if candidates is None:
                encoded_q = urllib.parse.quote(f"{query} filetype:{filetype}")
                url = (
                    f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                    f"&gsrsearch={encoded_q}&gsrnamespace=6&gsrlimit=8&prop=imageinfo"
                    f"&iiprop=url|mime|size&format=json"
                )
                data = self._throttled_get_json(url)
                candidates = []
                if data:
                    pages = data.get("query", {}).get("pages", {})
                    for page in pages.values():
                        imageinfo = page.get("imageinfo", [])
                        if not imageinfo:
                            continue
                        info = imageinfo[0]
                        candidates.append({
                            "url": str(info.get("url", "")),
                            "mime": str(info.get("mime", "")),
                            "width": str(info.get("width", 0) or 0),
                            "height": str(info.get("height", 0) or 0),
                        })
                self._query_cache[cache_key] = candidates

            for cand in candidates:
                file_url = cand["url"]
                mime = cand["mime"]
                w = int(cand["width"])
                h = int(cand["height"])

                if not file_url or file_url in used:
                    continue

                if filetype == "video" and ("video" in mime or file_url.endswith((".webm", ".mp4", ".ogv"))):
                    if self._download_file(file_url, target_path, min_bytes=5000):
                        used.add(file_url)
                        logger.info(f"Wikimedia video retrieved: {file_url}")
                        return target_path

                elif filetype == "bitmap" and ("image/jpeg" in mime or "image/png" in mime):
                    if w < 640 or h < 420:
                        continue
                    if self.fetch_direct_url_as_video(file_url, target_path, duration, camera, date_badge):
                        used.add(file_url)
                        logger.info(f"Wikimedia image animated ({w}x{h}): {file_url}")
                        return target_path
        return None

    def _download_file(self, url: str, path: str, min_bytes: int = 5000) -> bool:
        try:
            elapsed = time.time() - self._last_req_ts
            if elapsed < 0.25:
                time.sleep(0.25 - elapsed)
            self._last_req_ts = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.6 (open media research)"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            return os.path.exists(path) and os.path.getsize(path) >= min_bytes
        except Exception:
            return False
