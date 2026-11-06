"""Offline stand-in for a chat model. Scripted outputs / errors, used by every test."""

from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel


class _Runnable:
    def __init__(self, owner: FakeChatModel, schema: type[BaseModel]):
        self.owner, self.schema = owner, schema

    def invoke(self, messages: Any):
        self.owner.calls.append(messages)
        if self.owner.script:
            item = self.owner.script.popleft()
            if isinstance(item, Exception):
                raise item
            return item if isinstance(item, BaseModel) else self.schema.model_validate(item)
        return self.schema.model_validate(self.owner.default)


class FakeChatModel:
    """`script` items are consumed in order: dict/BaseModel -> returned, Exception -> raised."""

    def __init__(self, script: list | None = None, default: dict | None = None):
        self.script: deque = deque(script or [])
        self.default = default or {}
        self.calls: list = []

    def with_structured_output(self, schema: type[BaseModel]):
        return _Runnable(self, schema)
