from __future__ import annotations

import hashlib
import json
from typing import Protocol


class Cache(Protocol):
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value: dict) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self._data.get(key)

    def set(self, key: str, value: dict) -> None:
        self._data[key] = value


def make_key(*, schema_name: str, messages: list[tuple[str, str]], model_tag: str = "") -> str:
    payload = json.dumps([schema_name, model_tag, messages], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
