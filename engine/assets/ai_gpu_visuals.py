"""
engine/assets/ai_gpu_visuals.py - Colab GPU FLUX.1-schnell (Stills) & LTX-Video FP8 (Hero I2V)
Implements Stage-Gate GPU allocation:
  - Stage 4: FLUX.1-schnell FP8 (4-step) generates realistic documentary photos (~25% beats)
             using Anti-Virtual camera/lens prompts, then adds subtle FFmpeg film grain & zoom.
  - Stage 5: LTX-Video 0.9.7-distilled FP8 Image-to-Video animates strictly Hero Hook / Chapter
             opening keyframes (~5% beats, 8n+1 frames = 73 frames) with immediate VRAM unload.
"""
import gc
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

from engine.assets.motion import animate_image_to_video

logger = logging.getLogger("assets.ai_gpu_visuals")


class FluxStillGenerator:
    """FLUX.1-schnell documentary image generator (Colab GPU or HF Inference API)."""

    def __init__(self, hf_token: Optional[str] = None, width: int = 1920, height: int = 1080, fps: int = 25):
        self.hf_token = hf_token or os.environ.get("HF_TOKEN", "").strip() or None
        self.width = width
        self.height = height
        self.fps = fps
        self._pipe = None
        self._checked = False
        self._hf_api_exhausted = False

    def _has_cuda(self) -> bool:
        try:
            import diffusers  # noqa: F401
            import torch
            return bool(torch.cuda.is_available())
        except ImportError:
            return False

    def is_available(self) -> bool:
        return self._has_cuda() or (bool(self.hf_token) and not self._hf_api_exhausted)

    def _load(self) -> bool:
        if self._checked:
            return self._pipe is not None
        self._checked = True
        if not self._has_cuda():
            return False
        try:
            import torch
            from diffusers import FluxPipeline
            if self.hf_token:
                os.environ["HF_TOKEN"] = self.hf_token
            logger.info("Loading FLUX.1-schnell for documentary still fallback (VRAM Stage 4)...")
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                token=self.hf_token,
            )
            pipe.enable_model_cpu_offload()
            self._pipe = pipe
            return True
        except Exception as e:
            logger.debug(f"FLUX.1-schnell unavailable cleanly: {e}")
            return False

    def _generate_via_hf_api(self, prompt_en: str, out_img_path: str) -> Optional[str]:
        """Call Hugging Face Inference / Router API for FLUX.1-schnell (35mm documentary style)."""
        if not self.hf_token or self._hf_api_exhausted:
            return None
        doc_prompt = (
            f"{prompt_en[:260]}, 35mm Leica documentary photography, natural realistic lighting, "
            "subtle film grain, photojournalism, 16:9 widescreen, no text, no watermark"
        )
        endpoints = (
            (
                "https://router.huggingface.co/fal-ai/fal-ai/flux/schnell",
                {"prompt": doc_prompt, "image_size": "landscape_16_9", "num_inference_steps": 4},
            ),
            (
                "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                {"inputs": doc_prompt, "parameters": {"width": 1280, "height": 720, "num_inference_steps": 4}},
            ),
            (
                "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-3-medium-diffusers",
                {"inputs": doc_prompt, "parameters": {"width": 1280, "height": 720}},
            ),
        )
        for url, payload in endpoints:
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.hf_token}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=35) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    raw = resp.read()
                    if resp.status == 200 and "image" in ctype and len(raw) > 8000:
                        with open(out_img_path, "wb") as f:
                            f.write(raw)
                        return out_img_path
                    if resp.status == 200 and "json" in ctype:
                        data = json.loads(raw.decode("utf-8", errors="replace"))
                        img_url = None
                        if isinstance(data, dict):
                            imgs = data.get("images") or []
                            if imgs and isinstance(imgs[0], dict):
                                img_url = imgs[0].get("url")
                        if img_url:
                            with urllib.request.urlopen(urllib.request.Request(img_url), timeout=20) as ir:
                                img_bytes = ir.read()
                            if len(img_bytes) > 8000:
                                with open(out_img_path, "wb") as f:
                                    f.write(img_bytes)
                                return out_img_path
            except urllib.error.HTTPError as e:
                if e.code == 402:
                    logger.info("HF Inference API credit limit reached (HTTP 402); falling back to Pollinations.ai.")
                    self._hf_api_exhausted = True
                    return None
                logger.debug(f"HF Inference endpoint {url} returned HTTP {e.code}")
            except Exception as e:
                logger.debug(f"HF Inference endpoint {url} skipped: {e}")
        return None

    def generate_image_file(self, prompt_en: str, out_img_path: str, seed: int = 100) -> Optional[str]:
        if self._load():
            try:
                import torch
                gen = torch.Generator("cpu").manual_seed(seed)
                out = self._pipe(
                    prompt=prompt_en[:350],
                    width=1280,
                    height=720,
                    num_inference_steps=4,
                    guidance_scale=0.0,
                    generator=gen,
                ).images[0]
                out.save(out_img_path)
                return out_img_path if os.path.exists(out_img_path) else None
            except Exception as e:
                logger.warning(f"FLUX image generation failed: {e}")
        return self._generate_via_hf_api(prompt_en, out_img_path)

    def generate_still_clip(
        self,
        prompt_en: str,
        output_mp4: str,
        duration: float = 4.0,
        camera: str = "push_in",
        date_badge: str = "",
        seed: int = 100,
    ) -> Optional[str]:
        img_tmp = output_mp4 + ".flux.png"
        if self.generate_image_file(prompt_en, img_tmp, seed=seed):
            res = animate_image_to_video(
                img_tmp, output_mp4, duration=duration, width=self.width, height=self.height,
                fps=self.fps, camera=camera, date_badge=date_badge, add_film_grain=True,
            )
            if os.path.exists(img_tmp):
                os.remove(img_tmp)
            return res
        return None

    def unload(self) -> None:
        if self._pipe is not None:
            try:
                del self._pipe
            except Exception:
                pass
            self._pipe = None
        self._checked = False
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


class LtxVideoGenerator:
    """Colab GPU LTX-Video (0.9.7-distilled FP8) Image-to-Video strictly for Hero Hooks (~5% beats)."""

    def __init__(self, hf_token: Optional[str] = None, width: int = 1920, height: int = 1080, fps: int = 25):
        self.hf_token = hf_token or os.environ.get("HF_TOKEN", "").strip() or None
        self.width = width
        self.height = height
        self.fps = fps
        self._pipe = None
        self._checked = False

    def is_available(self) -> bool:
        try:
            import diffusers  # noqa: F401
            import torch
            return bool(torch.cuda.is_available())
        except ImportError:
            return False

    def _load(self) -> bool:
        if self._checked:
            return self._pipe is not None
        self._checked = True
        if not self.is_available():
            return False
        try:
            import torch
            from diffusers import LTXImageToVideoPipeline
            if self.hf_token:
                os.environ["HF_TOKEN"] = self.hf_token
            logger.info("Loading LTX-Video distilled FP8 for Hero Hook I2V (VRAM Stage 5)...")
            pipe = LTXImageToVideoPipeline.from_pretrained(
                "Lightricks/LTX-Video-0.9.7-distilled",
                torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                token=self.hf_token,
            )
            pipe.enable_model_cpu_offload()
            self._pipe = pipe
            return True
        except Exception as e:
            logger.debug(f"LTX-Video unavailable cleanly: {e}")
            return False

    def generate_i2v_clip(
        self,
        keyframe_image_path: str,
        motion_prompt: str,
        output_mp4: str,
        seed: int = 2026,
    ) -> Optional[str]:
        """Generate subtle 3s (73 frames, 8n+1 rule, dims / 32) documentary I2V motion clip."""
        if not keyframe_image_path or not os.path.exists(keyframe_image_path):
            return None
        if not self._load():
            return None
        try:
            import torch
            from diffusers.utils import export_to_video
            from PIL import Image
            img = Image.open(keyframe_image_path).convert("RGB").resize((768, 448))
            safe_prompt = (
                f"{motion_prompt[:180]}, slow camera push-in, subtle atmospheric motion, "
                "24fps realistic archival documentary footage"
            )
            gen = torch.Generator("cpu").manual_seed(seed)
            frames = self._pipe(
                image=img,
                prompt=safe_prompt,
                negative_prompt="fast erratic motion, morphing faces, distortion, cartoon, neon",
                width=768,
                height=448,
                num_frames=73,  # Strictly 8n+1 = 73 frames (~3.0s at 24fps)
                num_inference_steps=8,
                generator=gen,
            ).frames[0]
            raw_mp4 = output_mp4 + ".ltx_raw.mp4"
            export_to_video(frames, raw_mp4, fps=24)
            return raw_mp4 if os.path.exists(raw_mp4) else None
        except Exception as e:
            logger.warning(f"LTX I2V generation skipped cleanly: {e}")
            return None

    def unload(self) -> None:
        if self._pipe is not None:
            try:
                del self._pipe
            except Exception:
                pass
            self._pipe = None
        self._checked = False
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
