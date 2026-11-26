"""
engine/assets/nasa.py - NASA Image & Video Library Open Media Provider
Provides public-domain space, astronomy, Earth, and planetary photography/video without paid keys.
"""
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import List, Optional, Set

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.nasa")

_SPACE_KEYWORDS_RE = re.compile(
    r"\b(astronomy|space|planet|earth|moon|sun|solar|star|galaxy|mars|universe|cosmos|sky|orbit|eclipse|telescope|rocket|nebula|khagol)\b",
    re.IGNORECASE,
)


class NasaMediaProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 15, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "nasa_media_archive"

    def is_available(self) -> bool:
        return True

    @staticmethod
    def is_topic_relevant(queries: List[str]) -> bool:
        joined = " ".join(queries)
        return bool(_SPACE_KEYWORDS_RE.search(joined))

    def fetch_video(
        self,
        queries: List[str],
        target_path: str,
        min_duration: float = 5.0,
        used_urls: Optional[Set[str]] = None,
        camera: str = "push_in",
        date_badge: str = "",
    ) -> Optional[str]:
        if not self.is_topic_relevant(queries):
            return None

        used = used_urls if used_urls is not None else set()
        for query in queries:
            try:
                q_enc = urllib.parse.quote(query)
                url = f"https://images-api.nasa.gov/search?q={q_enc}&media_type=image&page_size=8"
                req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.5"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        continue
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    items = data.get("collection", {}).get("items", [])
                    for item in items:
                        links = item.get("links", [])
                        if not links:
                            continue
                        img_url = links[0].get("href")
                        if not img_url or img_url in used:
                            continue
                        tmp_img = target_path + ".nasa.jpg"
                        if self._download_file(img_url, tmp_img):
                            anim = animate_image_to_video(
                                tmp_img,
                                target_path,
                                duration=min_duration,
                                width=self.width,
                                height=self.height,
                                fps=self.fps,
                                camera=camera,
                                date_badge=date_badge,
                            )
                            if os.path.exists(tmp_img):
                                os.remove(tmp_img)
                            if anim:
                                used.add(img_url)
                                logger.info(f"NASA media animated: {img_url}")
                                return target_path
            except Exception as e:
                logger.debug(f"NASA lookup skipped for '{query}': {e}")
        return None

    def _download_file(self, url: str, path: str) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.5"})
            with urllib.request.urlopen(req, timeout=25) as resp, open(path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
            return os.path.exists(path) and os.path.getsize(path) > 15000
        except Exception:
            return False
