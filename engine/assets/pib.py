"""
engine/assets/pib.py - Press Information Bureau (pib.gov.in) Watermark-Free Official Media Provider
Searches official Indian government / constitutional / public event imagery via Wikimedia/PIB endpoints.
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

logger = logging.getLogger("assets.pib")


class PIBIndiaProvider(VisualAssetProvider):
    """Fetch watermark-free official Indian public-domain photos (PIB / Govt / Constitutional)."""

    def __init__(self, timeout: int = 15, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "pib_india_official"

    def is_available(self) -> bool:
        return True

    def is_topic_relevant(self, queries: List[str]) -> bool:
        joined = " ".join(queries).lower()
        india_civic_terms = (
            "india", "supreme court", "parliament", "minister", "cji", "election",
            "protest", "delhi", "mumbai", "cabinet", "pib", "government", "commission",
            "pradhan", "modi", "court", "budget", "isro", "policy",
        )
        return any(tok in joined for tok in india_civic_terms)

    def fetch_video(
        self,
        queries: List[str],
        target_path: str,
        min_duration: float = 5.0,
        used_urls: Optional[Set[str]] = None,
        camera: str = "push_in",
        date_badge: str = "",
    ) -> Optional[str]:
        if used_urls is None:
            used_urls = set()
        # Query Wikimedia Commons specifically filtered to Press Information Bureau India attributions
        for q in queries[:2]:
            scoped = f"\"Press Information Bureau\" {q}"
            encoded = urllib.parse.quote(scoped)
            api_url = (
                f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                f"&gsrsearch={encoded}&gsrnamespace=6&gsrlimit=6"
                f"&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=1920&format=json&utf8=1"
            )
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "AIDocEngine/3.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        continue
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                pages = list((data.get("query", {}).get("pages", {}) or {}).values())
                for page in pages:
                    infos = page.get("imageinfo") or []
                    if not infos:
                        continue
                    info = infos[0]
                    mime = info.get("mime", "")
                    w = int(info.get("width", 0))
                    h = int(info.get("height", 0))
                    url = info.get("thumburl") or info.get("url") or ""
                    if not url or url in used_urls or "image/" not in mime:
                        continue
                    if w < 800 or h < 450:
                        continue
                    tmp_img = target_path + ".pib.jpg"
                    req_img = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/3.0"})
                    with urllib.request.urlopen(req_img, timeout=self.timeout) as ir, open(tmp_img, "wb") as f:
                        f.write(ir.read())
                    if os.path.exists(tmp_img) and os.path.getsize(tmp_img) > 15000:
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
                            used_urls.add(url)
                            return target_path
                    elif os.path.exists(tmp_img):
                        os.remove(tmp_img)
            except Exception as e:
                logger.debug(f"PIB provider lookup skipped: {e}")
        return None
