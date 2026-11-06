"""LLM client for offline evaluation (no Django): Groq primary, Gemini fallback, paced + cached."""

from __future__ import annotations

import os
from pathlib import Path

from apps.llm.client import LLMClient, Provider

from .caches import FileCache, Paced

DEFAULTS = {
    "groq": ("groq", os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"), "GROQ_API_KEY"),
    "gemini": (
        "google_genai",
        os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        "GOOGLE_API_KEY",
    ),
}


def make_llm(
    primary: str, cache_dir: str | Path, min_interval: float = 2.5, fallback: bool = True
) -> LLMClient:
    from langchain.chat_models import init_chat_model

    order = [primary] + ([n for n in DEFAULTS if n != primary] if fallback else [])
    providers = []
    for name in order:
        provider, model, key_env = DEFAULTS[name]
        if not os.environ.get(key_env):
            continue
        chat = init_chat_model(model, model_provider=provider, temperature=0)
        providers.append(Provider(name, Paced(chat, min_interval)))
    if not providers:
        raise RuntimeError(
            "No LLM API key found. Set GROQ_API_KEY and/or GOOGLE_API_KEY (free tiers)."
        )
    return LLMClient(providers, cache=FileCache(cache_dir), max_retries=4, max_wait=90)
