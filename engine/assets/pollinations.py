"""
engine/assets/pollinations.py - Keyless AI 2D Illustration & Documentary Artwork Provider
Generates custom 2D/editorial illustrations via Pollinations.ai and animates them smoothly.
"""
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from engine.assets.base import VisualAssetProvider
from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.pollinations")


class PollinationsAIProvider(VisualAssetProvider):
    def __init__(self, timeout: int = 35, width: int = 1920, height: int = 1080, fps: int = 25):
        self.timeout = timeout
        self.width = width
        self.height = height
        self.fps = fps
        self._last_req_ts = 0.0

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
        for attempt in range(2):
            elapsed = time.time() - self._last_req_ts
            if elapsed < 1.6:
                time.sleep(1.6 - elapsed)
            self._last_req_ts = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AIDocEngine/3.0"})
                with urllib.request.urlopen(req, timeout=max(30, self.timeout)) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status == 200 and "image" in ctype:
                        with open(tmp_img, "wb") as f:
                            while chunk := resp.read(65536):
                                f.write(chunk)
                        break
            except urllib.error.HTTPError as e:
                if e.code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(3.0)
                    continue
                logger.debug(f"Pollinations HTTP {e.code} skipped: {e}")
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(2.0)
                    continue
                logger.debug(f"Pollinations generation skipped: {e}")
                break

        if os.path.exists(tmp_img) and os.path.getsize(tmp_img) > 15000:
            # Trim bottom 9% watermark strip (pollinations.ai badge) cleanly before Ken Burns animation
            cropped_img = target_path + ".clean.jpg"
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp_img, "-vf", "crop=iw:ih*0.91:0:0", cropped_img],
                capture_output=True,
            )
            anim_src = cropped_img if (os.path.exists(cropped_img) and os.path.getsize(cropped_img) > 5000) else tmp_img
            anim = animate_image_to_video(
                anim_src,
                target_path,
                duration=min_duration,
                width=self.width,
                height=self.height,
                fps=self.fps,
                camera=camera,
                date_badge=date_badge,
            )
            for tmpf in (tmp_img, cropped_img):
                if os.path.exists(tmpf):
                    os.remove(tmpf)
            if anim:
                logger.info("Pollinations custom 2D artwork animated successfully.")
                return target_path
        elif os.path.exists(tmp_img):
            os.remove(tmp_img)

        return None
