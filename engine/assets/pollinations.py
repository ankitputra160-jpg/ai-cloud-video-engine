"""
engine/assets/pollinations.py - Keyless AI 2D Illustration & Documentary Artwork Provider
Generates custom 2D/editorial illustrations via Pollinations.ai and animates them smoothly.
"""
import logging
import os
import urllib.parse
import urllib.request
from typing import List, Optional

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.pollinations")


class PollinationsAIProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 25, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps

    @property
    def name(self) -> str:
        return "pollinations_ai_2d"

    def is_available(self) -> bool:
        return True

    def fetch_video(
        self,
        queries: List[str],
        target_path: str,
        min_duration: float = 5.0,
        ai_prompt: Optional[str] = None,
        camera: str = "push_in",
        date_badge: str = "",
        seed: int = 42,
    ) -> Optional[str]:
        prompt_text = ai_prompt or (queries[0] if queries else "Historical scientific documentary illustration")
        prompt_text = prompt_text[:280]
        encoded = urllib.parse.quote(prompt_text)

        gen_w = 1280 if self.width >= 1280 else self.width
        gen_h = 720 if self.height >= 720 else self.height
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={gen_w}&height={gen_h}&nologo=true&seed={seed}"

        tmp_img = target_path + ".ai.jpg"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIDocEngine/2.5"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                if resp.status == 200 and "image" in ctype:
                    with open(tmp_img, "wb") as f:
                        while chunk := resp.read(65536):
                            f.write(chunk)
        except Exception as e:
            logger.debug(f"Pollinations generation skipped: {e}")

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
                logger.info("Pollinations custom 2D artwork animated successfully.")
                return target_path
        elif os.path.exists(tmp_img):
            os.remove(tmp_img)

        return None
