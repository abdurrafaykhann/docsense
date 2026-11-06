"""LLMClient: structured output with retry/backoff on 429, provider failover and caching.

Primary (Groq) -> fallback (Gemini). Rate-limit waits honour the provider's retry-after
header up to `max_wait`; longer waits trigger immediate failover instead of blocking.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from .cache import Cache, MemoryCache, make_key
from .errors import LLMUnavailable, classify

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
Messages = list[tuple[str, str]]  # [("system", "..."), ("human", "...")]


@dataclass
class Provider:
    name: str
    model: Any  # a LangChain BaseChatModel (or FakeChatModel)


@dataclass
class UsageRecord:
    provider: str
    schema: str
    status: str  # ok | rate_limited | error | cache_hit
    latency_s: float = 0.0
    attempt: int = 1
    prompt_chars: int = 0


@dataclass
class LLMClient:
    providers: list[Provider]
    cache: Cache = field(default_factory=MemoryCache)
    max_retries: int = 3
    max_wait: float = 30.0
    sleep: Callable[[float], None] = time.sleep
    on_usage: Callable[[UsageRecord], None] | None = None

    _chars: int = 0

    def _record(self, rec: UsageRecord) -> None:
        rec.prompt_chars = self._chars
        if self.on_usage:
            self.on_usage(rec)

    def structured(self, schema: type[T], messages: Messages, *, cache_extra: str = "") -> T:
        key = make_key(schema_name=schema.__name__, messages=messages, model_tag=cache_extra)
        self._chars = sum(len(c) for _, c in messages)
        hit = self.cache.get(key)
        if hit is not None:
            self._record(UsageRecord("cache", schema.__name__, "cache_hit"))
            return schema.model_validate(hit)

        last_exc: Exception | None = None
        for provider in self.providers:
            result = self._try_provider(provider, schema, messages)
            if isinstance(result, Exception):
                last_exc = result
                continue
            self.cache.set(key, result.model_dump(mode="json"))
            return result
        raise LLMUnavailable(f"all providers failed: {last_exc!r}") from last_exc

    def _try_provider(self, provider: Provider, schema: type[T], messages: Messages):
        """Return the parsed result, or the Exception that made us give up on this provider."""
        runnable = provider.model.with_structured_output(schema)
        last: Exception = RuntimeError("no attempts made")
        for attempt in range(1, self.max_retries + 1):
            started = time.monotonic()
            try:
                out = runnable.invoke(messages)
                out = out if isinstance(out, schema) else schema.model_validate(out)
                elapsed = time.monotonic() - started
                self._record(UsageRecord(provider.name, schema.__name__, "ok", elapsed, attempt))
                return out
            except Exception as exc:  # classified below
                last = exc
                limited, retry_after = classify(exc)
                status = "rate_limited" if limited else "error"
                elapsed = time.monotonic() - started
                self._record(UsageRecord(provider.name, schema.__name__, status, elapsed, attempt))
                if not limited:
                    log.warning("%s failed: %r", provider.name, exc)
                    return exc
                delay = retry_after if retry_after is not None else min(2**attempt, 16)
                delay += random.uniform(0, 0.25 * max(delay, 1))  # jitter
                if delay > self.max_wait or attempt == self.max_retries:
                    log.warning("%s rate limited (wait %.1fs) -> failover", provider.name, delay)
                    return exc
                self.sleep(delay)
        return last


def build_default_client(settings=None) -> LLMClient:
    """Construct the client from Django settings. `fake` yields a deterministic offline model."""
    from django.conf import settings as dj_settings

    settings = settings or dj_settings
    if settings.LLM_PROVIDER == "fake":
        from .fake import FakeChatModel

        return LLMClient([Provider("fake", FakeChatModel())], on_usage=db_usage_logger)

    from langchain.chat_models import init_chat_model

    order = [settings.LLM_PRIMARY, settings.LLM_FALLBACK]
    if settings.LLM_PROVIDER == "gemini":
        order.reverse()
    providers = [
        Provider(
            c["provider"],
            init_chat_model(c["model"], model_provider=c["provider"], temperature=0),
        )
        for c in order
    ]
    from .cache import DbCache

    return LLMClient(
        providers,
        cache=DbCache(),
        max_retries=settings.LLM_MAX_RETRIES,
        max_wait=settings.LLM_MAX_WAIT_SECONDS,
        on_usage=db_usage_logger,
    )


def db_usage_logger(rec: UsageRecord) -> None:
    """Persist one LLMUsage row per attempt (best effort: never break extraction)."""
    from . import context
    from .models import LLMUsage

    try:
        ctx = context.current()
        LLMUsage.objects.create(
            provider=rec.provider,
            schema=rec.schema,
            status=rec.status,
            latency_s=rec.latency_s,
            attempt=rec.attempt,
            prompt_chars=rec.prompt_chars,
            workspace_id=ctx.get("workspace_id"),
            document_id=ctx.get("document_id"),
        )
    except Exception:  # noqa: BLE001
        log.exception("could not record LLM usage")
