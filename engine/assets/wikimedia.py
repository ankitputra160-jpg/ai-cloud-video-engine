"""
engine/assets/wikimedia.py - Wikimedia Commons Open Media Provider
Retrieves public-domain & Creative Commons videos AND high-resolution historical/scientific
photos (automatically animated with Ken Burns 2D camera motion) with zero API keys required.
"""
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import List, Optional, Set

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.wikimedia")


class WikimediaCommonsProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 15, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "wikimedia_commons"

    def is_available(self) -> bool:
        return True

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

        # Pass 1: Video clips (unless caller explicitly prefers curated 2D still-image animations)
        if not prefer_images:
            res = self._search_media(queries, target_path, "video", used, min_duration, camera, date_badge)
            if res:
                return res

        # Pass 2: High-resolution historical/encyclopedic images -> Ken Burns animation
        res = self._search_media(queries, target_path, "bitmap", used, min_duration, camera, date_badge)
        if res:
            return res

        # Pass 3: Video fallback if prefer_images missed
        if prefer_images:
            return self._search_media(queries, target_path, "video", used, min_duration, camera, date_badge)
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
            try:
                encoded_q = urllib.parse.quote(f"{query} filetype:{filetype}")
                url = (
                    f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                    f"&gsrsearch={encoded_q}&gsrnamespace=6&gsrlimit=8&prop=imageinfo"
                    f"&iiprop=url|mime|size&format=json"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.5 (open media research)"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        continue
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    pages = data.get("query", {}).get("pages", {})
                    for page in pages.values():
                        imageinfo = page.get("imageinfo", [])
                        if not imageinfo:
                            continue
                        info = imageinfo[0]
                        file_url = info.get("url")
                        mime = info.get("mime", "")
                        w = int(info.get("width", 0) or 0)
                        h = int(info.get("height", 0) or 0)

                        if not file_url or file_url in used:
                            continue

                        if filetype == "video" and ("video" in mime or file_url.endswith((".webm", ".mp4", ".ogv"))):
                            if self._download_file(file_url, target_path):
                                used.add(file_url)
                                logger.info(f"Wikimedia video retrieved: {file_url}")
                                return target_path

                        elif filetype == "bitmap" and ("image/jpeg" in mime or "image/png" in mime):
                            # Enforce high-resolution landscape/editorial images (>= 800px)
                            if w < 800 or h < 450:
                                continue
                            ext = ".png" if "png" in mime else ".jpg"
                            tmp_img = target_path + f".commons{ext}"
                            if self._download_file(file_url, tmp_img, min_bytes=20000):
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
                                    used.add(file_url)
                                    logger.info(f"Wikimedia image animated ({w}x{h}): {file_url}")
                                    return target_path
                            elif os.path.exists(tmp_img):
                                os.remove(tmp_img)
            except Exception as e:
                logger.debug(f"Wikimedia {filetype} note for '{query}': {e}")
        return None

    def _download_file(self, url: str, path: str, min_bytes: int = 5000) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.5"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            return os.path.exists(path) and os.path.getsize(path) >= min_bytes
        except Exception:
            return False
