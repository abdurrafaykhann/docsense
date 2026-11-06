"""Disk caches so repeated evaluation runs cost zero OCR time and zero LLM requests."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
from apps.validation.grounding import Word


class CachedOCR:
    """Wraps an OCR engine; results keyed by image content + engine name."""

    def __init__(self, engine, cache_dir: str | Path, name: str = "doctr"):
        self.engine, self.name = engine, name
        self.dir = Path(cache_dir) / "ocr"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = self.misses = 0

    def read(self, image: np.ndarray, page: int = 1) -> list[Word]:
        key = hashlib.sha1(image.tobytes() + self.name.encode()).hexdigest()
        path = self.dir / f"{key}.json"
        if path.exists():
            self.hits += 1
            words = [Word.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]
            for w in words:
                w.page = page
            return words
        self.misses += 1
        words = self.engine.read(image, page=page)
        path.write_text(json.dumps([w.as_dict() for w in words]), encoding="utf-8")
        return words


class FileCache:
    """LLM response cache (implements apps.llm.cache.Cache) persisted as JSON files."""

    def __init__(self, cache_dir: str | Path):
        self.dir = Path(cache_dir) / "llm"
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict | None:
        p = self.dir / f"{key}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def set(self, key: str, value: dict) -> None:
        (self.dir / f"{key}.json").write_text(json.dumps(value), encoding="utf-8")


class Paced:
    """Proxy for a chat model that enforces a minimum interval between requests (free tier)."""

    def __init__(self, model, min_interval: float, sleep=time.sleep, clock=time.monotonic):
        self.model, self.min_interval = model, min_interval
        self._last: float | None = None
        self._sleep, self._clock = sleep, clock

    def with_structured_output(self, schema):
        runnable = self.model.with_structured_output(schema)
        outer = self

        class _R:
            def invoke(self, messages):
                wait = outer.min_interval - (outer._clock() - (outer._last or 0.0))
                if outer._last is not None and wait > 0:
                    outer._sleep(wait)
                try:
                    return runnable.invoke(messages)
                finally:
                    outer._last = outer._clock()

        return _R()
