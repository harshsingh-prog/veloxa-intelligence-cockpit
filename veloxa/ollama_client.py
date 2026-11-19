"""Optional local Ollama adapter. Everything works without it; with it, text is only ever *re-phrased*
and must pass guard.check() (see llm.safe_rewrite)."""
from __future__ import annotations

import functools
import os

import requests


def base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def model() -> str:
    return os.getenv("VELOXA_MODEL", "qwen2.5:14b-instruct")


@functools.lru_cache(maxsize=1)
def _reachable_cached(url: str, bucket: int) -> bool:
    try:
        return requests.get(url + "/api/tags", timeout=0.6).ok
    except Exception:
        return False


def reachable() -> bool:
    import time
    return _reachable_cached(base_url(), int(time.time() // 30))  # re-check every 30 s


def generate(prompt: str, timeout: float = 20.0) -> str | None:
    if not reachable():
        return None
    try:
        r = requests.post(f"{base_url()}/api/generate", timeout=timeout, json={
            "model": model(), "prompt": prompt, "stream": False, "options": {"temperature": 0, "top_p": 0.1, "seed": 7}})
        r.raise_for_status()
        return (r.json().get("response") or "").strip() or None
    except Exception:
        return None
