"""
engine/assets/qc_visual.py - Pre-Render Visual Quality Gatekeeper & Colab OpenCLIP Semantic Filter
Ensures retrieved footage/images meet minimum resolution & landscape framing rules,
and optionally scores visual-to-prompt semantic alignment via OpenCLIP (ViT-B-32) on GPU.
"""
import gc
import json
import logging
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("assets.qc_visual")


def probe_visual_dimensions(media_path: str) -> Tuple[int, int]:
    """Return (width, height) of an image or video asset via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", media_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            streams = json.loads(res.stdout).get("streams", [])
            if streams:
                return int(streams[0].get("width", 0)), int(streams[0].get("height", 0))
    except Exception:
        pass
    return 0, 0


def validate_visual_dimensions(
    media_path: str,
    min_width: int = 960,
    min_height: int = 540,
    allow_portrait_composite: bool = True,
) -> bool:
    """Reject tiny blurry thumbnails or degenerate broken visual files before rendering."""
    w, h = probe_visual_dimensions(media_path)
    if w <= 0 or h <= 0:
        return False
    if allow_portrait_composite:
        return max(w, h) >= min_width and min(w, h) >= min_height * 0.75
    return w >= min_width and h >= min_height and (w / h) >= 1.25


class SemanticClipChecker:
    """GPU-optional OpenCLIP ViT-B-32 semantic filter checking visual alignment vs. English prompt."""

    def __init__(self, min_similarity: float = 0.21):
        self.min_similarity = min_similarity
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._checked = False

    def is_available(self) -> bool:
        try:
            import open_clip  # noqa: F401
            import torch
            return bool(torch.cuda.is_available())
        except ImportError:
            return False

    def _load(self) -> bool:
        if self._checked:
            return self._model is not None
        self._checked = True
        if not self.is_available():
            return False
        try:
            import open_clip
            model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
            self._model = model.to("cuda").eval()
            self._preprocess = preprocess
            self._tokenizer = open_clip.get_tokenizer("ViT-B-32")
            logger.info("Loaded OpenCLIP ViT-B-32 for semantic visual QC.")
            return True
        except Exception as e:
            logger.debug(f"OpenCLIP unavailable cleanly: {e}")
            return False

    def score_image_vs_prompt(self, image_path: str, prompt_en: str) -> Optional[float]:
        """Compute cosine similarity between image frame and English scene description."""
        if not self._load():
            return None
        try:
            import torch
            from PIL import Image
            img = self._preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to("cuda")
            txt = self._tokenizer([prompt_en[:200]]).to("cuda")
            with torch.no_grad():
                img_f = self._model.encode_image(img)
                txt_f = self._model.encode_text(txt)
                img_f = img_f / img_f.norm(dim=-1, keepdim=True)
                txt_f = txt_f / txt_f.norm(dim=-1, keepdim=True)
                score = float((img_f @ txt_f.T).item())
            return round(score, 3)
        except Exception as e:
            logger.debug(f"OpenCLIP scoring skipped: {e}")
            return None

    def passes_semantic_check(self, image_path: str, prompt_en: str) -> bool:
        score = self.score_image_vs_prompt(image_path, prompt_en)
        if score is None:
            return True
        if score < self.min_similarity:
            logger.info(f"OpenCLIP rejected mismatched visual (score={score:.2f} < {self.min_similarity}): {prompt_en[:50]}")
            return False
        return True

    def unload(self) -> None:
        for attr in ("_model", "_preprocess", "_tokenizer"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    del obj
                except Exception:
                    pass
                setattr(self, attr, None)
        self._checked = False
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
