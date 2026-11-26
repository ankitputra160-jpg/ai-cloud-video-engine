"""
engine/assets/openverse.py - Openverse Creative Commons & Public Domain Media Provider
Fetches watermark-free landscape photographs (cc0, pdm, by) via api.openverse.org.
"""
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import List, Optional, Set

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.openverse")


class OpenverseProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 15, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "openverse_cc"

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
    ) -> Optional[str]:
        if used_urls is None:
            used_urls = set()

        for query in queries[:2]:
            q_enc = urllib.parse.quote(query)
            url = (
                f"https://api.openverse.org/v1/images/?q={q_enc}"
                f"&license=cc0,pdm,by,by-sa&aspect_ratio=wide&page_size=8"
            )
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/3.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        continue
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                for item in data.get("results", []):
                    img_url = item.get("url") or ""
                    w = int(item.get("width") or 0)
                    h = int(item.get("height") or 0)
                    if not img_url or img_url in used_urls:
                        continue
                    if w and w < 960:
                        continue
                    if h and (w / max(1, h)) < 1.15:
                        continue
                    tmp_img = target_path + ".ov.jpg"
                    try:
                        dreq = urllib.request.Request(img_url, headers={"User-Agent": "AIDocEngine/3.0"})
                        with urllib.request.urlopen(dreq, timeout=self.timeout) as ir, open(tmp_img, "wb") as out:
                            if ir.status == 200 and "image" in ir.headers.get("Content-Type", ""):
                                out.write(ir.read())
                        if os.path.exists(tmp_img) and os.path.getsize(tmp_img) > 15_000:
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
                                used_urls.add(img_url)
                                return target_path
                        elif os.path.exists(tmp_img):
                            os.remove(tmp_img)
                    except Exception:
                        if os.path.exists(tmp_img):
                            os.remove(tmp_img)
            except Exception as e:
                logger.debug(f"Openverse lookup skipped: {e}")
        return None
