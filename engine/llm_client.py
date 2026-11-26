"""
engine/llm_client.py - Unified Local (Gemma-3 CUDA/llama.cpp) & Free Cloud API LLM Client
Supports:
  - Default free local Gemma-3-12B-IT (T4 15GB) / Gemma-3-27B-IT (L4 24GB+) via llama-cpp-python or llama-server
  - Optional Gemini (GEMINI_API_KEY) and Groq (GROQ_API_KEY) free cloud APIs
  - Explicit Stage-Gate VRAM unload (del model + gc.collect + torch.cuda.empty_cache)
"""
import gc
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("llm_client")

DEFAULT_GEMMA_T4_REPO = "bartowski/google_gemma-3-12b-it-GGUF"
DEFAULT_GEMMA_T4_FILE = "*Q4_K_M.gguf"
DEFAULT_GEMMA_L4_REPO = "bartowski/google_gemma-3-27b-it-GGUF"
DEFAULT_GEMMA_L4_FILE = "*Q4_K_M.gguf"


class UnifiedLLMClient:
    """Manages local Gemma-3 GGUF inference and optional Gemini/Groq API fallback."""

    def __init__(
        self,
        llm_mode: str = "auto",
        gemini_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        hf_token: Optional[str] = None,
        llama_server_url: Optional[str] = None,
    ):
        self.llm_mode = (llm_mode or "auto").lower()
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "").strip() or None
        self.groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY", "").strip() or None
        self.hf_token = hf_token or os.environ.get("HF_TOKEN", "").strip() or None
        self.llama_server_url = (
            llama_server_url
            or os.environ.get("LLAMA_SERVER_URL", "").strip()
            or None
        )
        self._local_llama = None
        self._local_checked = False

    def is_llm_available(self) -> bool:
        """Return True if at least one cloud API key, llama-server, or GPU local Gemma runtime is usable."""
        if self.llm_mode == "deterministic":
            return False
        if self.llm_mode in ("gemini", "auto") and self.gemini_api_key:
            return True
        if self.llm_mode in ("groq", "auto") and self.groq_api_key:
            return True
        if self.llama_server_url:
            return True
        if self.llm_mode in ("local_gemma3", "auto") and self._can_use_local_gemma():
            return True
        return False

    def _detect_gpu_vram_gb(self) -> float:
        try:
            import torch
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                return round(props.total_memory / (1024 ** 3), 1)
        except Exception:
            pass
        return 0.0

    def _can_use_local_gemma(self) -> bool:
        if self._local_llama is not None:
            return True
        try:
            import llama_cpp  # noqa: F401
            return self._detect_gpu_vram_gb() >= 11.0
        except ImportError:
            return False

    def _load_local_gemma(self):
        if self._local_checked:
            return self._local_llama
        self._local_checked = True
        try:
            from llama_cpp import Llama
        except ImportError:
            return None

        vram_gb = self._detect_gpu_vram_gb()
        if vram_gb < 11.0:
            logger.info("Skipping local Gemma-3 load (GPU VRAM < 11 GB).")
            return None

        if self.hf_token:
            os.environ["HF_TOKEN"] = self.hf_token

        use_27b = vram_gb >= 21.0
        repo_id = DEFAULT_GEMMA_L4_REPO if use_27b else DEFAULT_GEMMA_T4_REPO
        filename = DEFAULT_GEMMA_L4_FILE if use_27b else DEFAULT_GEMMA_T4_FILE

        try:
            logger.info(f"Loading local Gemma-3 ({'27B' if use_27b else '12B'} Q4_K_M) on {vram_gb} GB GPU...")
            self._local_llama = Llama.from_pretrained(
                repo_id=repo_id,
                filename=filename,
                n_gpu_layers=-1,
                n_ctx=8192,
                verbose=False,
            )
            logger.info("Local Gemma-3 ready for script generation.")
            return self._local_llama
        except Exception as e:
            logger.warning(f"Local Gemma-3 load failed: {e}")
            return None

    def unload(self) -> None:
        """Unload local GPU LLM cleanly to free VRAM for TTS / Visual stages."""
        if self._local_llama is not None:
            try:
                del self._local_llama
            except Exception:
                pass
            self._local_llama = None
        self._local_checked = False
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.65,
        max_tokens: int = 3500,
        json_mode: bool = False,
    ) -> Optional[str]:
        """Generate completion using configured backend priority without crashing on transient errors."""
        if self.llm_mode == "deterministic":
            return None

        backends: List[str]
        if self.llm_mode == "local_gemma3":
            backends = ["llama_server", "local_gemma3", "groq", "gemini"]
        elif self.llm_mode == "gemini":
            backends = ["gemini", "groq", "local_gemma3"]
        elif self.llm_mode == "groq":
            backends = ["groq", "gemini", "local_gemma3"]
        else:
            # 'auto': fast free cloud keys if provided, else local Gemma-3 on Colab GPU
            backends = ["groq", "gemini", "llama_server", "local_gemma3"]

        for backend in backends:
            res: Optional[str] = None
            if backend == "groq" and self.groq_api_key:
                res = self._call_groq(prompt, system_prompt, temperature, max_tokens, json_mode)
            elif backend == "gemini" and self.gemini_api_key:
                res = self._call_gemini(prompt, system_prompt, temperature, max_tokens, json_mode)
            elif backend == "llama_server" and self.llama_server_url:
                res = self._call_llama_server(prompt, system_prompt, temperature, max_tokens, json_mode)
            elif backend == "local_gemma3":
                res = self._call_local_gemma(prompt, system_prompt, temperature, max_tokens, json_mode)
            if res:
                return res
        return None

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.55,
        max_tokens: int = 4096,
    ) -> Optional[Any]:
        """Request strict JSON output and extract valid JSON object or array cleanly."""
        raw = self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        if not raw:
            return None
        return self.extract_json_payload(raw)

    @staticmethod
    def extract_json_payload(raw: str) -> Optional[Any]:
        """Extract JSON object or array safely from raw LLM response (handles ```json fences)."""
        if not raw:
            return None
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE | re.MULTILINE)
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    continue
        return None

    def _call_groq(
        self, prompt: str, system_prompt: str, temperature: float, max_tokens: int, json_mode: bool
    ) -> Optional[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body: Dict[str, Any] = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    return payload["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                logger.warning(f"Groq HTTP {e.code}: {e.reason}")
                break
            except Exception as e:
                logger.debug(f"Groq request skipped: {e}")
                break
        return None

    def _call_gemini(
        self, prompt: str, system_prompt: str, temperature: float, max_tokens: int, json_mode: bool
    ) -> Optional[str]:
        full_prompt = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
        gen_cfg: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"

        for model in ("gemini-2.5-flash", "gemini-2.0-flash"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
            for attempt in range(2):
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps({
                            "contents": [{"parts": [{"text": full_prompt}]}],
                            "generationConfig": gen_cfg,
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        payload = json.loads(resp.read().decode("utf-8"))
                        return payload["candidates"][0]["content"]["parts"][0]["text"]
                except urllib.error.HTTPError as e:
                    if e.code == 429 and attempt == 0:
                        time.sleep(3)
                        continue
                    logger.debug(f"Gemini {model} HTTP {e.code}")
                    break
                except Exception as e:
                    logger.debug(f"Gemini {model} skipped: {e}")
                    break
        return None

    def _call_llama_server(
        self, prompt: str, system_prompt: str, temperature: float, max_tokens: int, json_mode: bool
    ) -> Optional[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body: Dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            url = self.llama_server_url.rstrip("/") + "/v1/chat/completions"
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
        except Exception as e:
            logger.debug(f"llama-server request failed: {e}")
            return None

    def _call_local_gemma(
        self, prompt: str, system_prompt: str, temperature: float, max_tokens: int, json_mode: bool
    ) -> Optional[str]:
        llama = self._load_local_gemma()
        if llama is None:
            return None
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        kwargs: Dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            out = llama.create_chat_completion(**kwargs)
            return out["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Local Gemma-3 completion error: {e}")
            return None
