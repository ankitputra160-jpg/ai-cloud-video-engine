"""
engine/assets/archive_org.py - Internet Archive Public Domain Footage & Historical Scan Provider
Fetches watermark-free archival video reels and vintage historical photographs via archive.org API.
"""
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import List, Optional, Set

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.archive_org")


class InternetArchiveProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 18, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "internet_archive"

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
            q_enc = urllib.parse.quote(f"({query}) AND mediatype:(movies OR image)")
            search_url = (
                f"https://archive.org/advancedsearch.php?q={q_enc}"
                f"&fl[]=identifier,mediatype&rows=5&page=1&output=json"
            )
            try:
                req = urllib.request.Request(search_url, headers={"User-Agent": "AIDocEngine/3.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        continue
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                docs = data.get("response", {}).get("docs", [])
                for doc in docs:
                    ident = doc.get("identifier")
                    if not ident:
                        continue
                    meta_url = f"https://archive.org/metadata/{urllib.parse.quote(ident)}/files"
                    mreq = urllib.request.Request(meta_url, headers={"User-Agent": "AIDocEngine/3.0"})
                    with urllib.request.urlopen(mreq, timeout=self.timeout) as mresp:
                        if mresp.status != 200:
                            continue
                        files_data = json.loads(mresp.read().decode("utf-8", errors="replace")).get("result", [])

                    # Prefer moderate MP4 clips (< 20 MB) or crisp JPG archival scans
                    for fmeta in files_data:
                        name = fmeta.get("name", "")
                        size = int(fmeta.get("size") or 0)
                        low = name.lower()
                        file_url = f"https://archive.org/download/{ident}/{urllib.parse.quote(name)}"
                        if file_url in used_urls:
                            continue

                        if low.endswith(".mp4") and 100_000 < size < 20_000_000:
                            dreq = urllib.request.Request(file_url, headers={"User-Agent": "AIDocEngine/3.0"})
                            with urllib.request.urlopen(dreq, timeout=max(20, self.timeout)) as dr, open(target_path, "wb") as out:
                                out.write(dr.read())
                            if os.path.exists(target_path) and os.path.getsize(target_path) > 50_000:
                                used_urls.add(file_url)
                                return target_path

                        if low.endswith((".jpg", ".jpeg", ".png")) and 20_000 < size < 8_000_000 and "thumb" not in low:
                            tmp_img = target_path + ".ia.jpg"
                            dreq = urllib.request.Request(file_url, headers={"User-Agent": "AIDocEngine/3.0"})
                            with urllib.request.urlopen(dreq, timeout=self.timeout) as dr, open(tmp_img, "wb") as out:
                                out.write(dr.read())
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
                                    used_urls.add(file_url)
                                    return target_path
                            elif os.path.exists(tmp_img):
                                os.remove(tmp_img)
            except Exception as e:
                logger.debug(f"Archive.org lookup skipped: {e}")
        return None
