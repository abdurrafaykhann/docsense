import pytest
from pydantic import BaseModel

from apps.llm.cache import MemoryCache
from apps.llm.client import LLMClient, Provider, UsageRecord, build_default_client
from apps.llm.errors import LLMUnavailable, RateLimited, classify
from apps.llm.fake import FakeChatModel


class Out(BaseModel):
    vendor: str = "x"
    total: float = 0


MSGS = [("system", "s"), ("human", "h")]


def client(*models, **kw):
    sleeps = []
    c = LLMClient([Provider(n, m) for n, m in models], sleep=sleeps.append, **kw)
    return c, sleeps


def test_returns_structured_output():
    c, _ = client(("groq", FakeChatModel([{"vendor": "ACME", "total": 118}])))
    assert c.structured(Out, MSGS) == Out(vendor="ACME", total=118)


def test_retries_on_429_then_succeeds_and_honours_retry_after():
    m = FakeChatModel([RateLimited(retry_after=2.0), {"vendor": "ok"}])
    c, sleeps = client(("groq", m))
    assert c.structured(Out, MSGS).vendor == "ok"
    assert len(sleeps) == 1 and 2.0 <= sleeps[0] <= 2.6


def test_fails_over_to_fallback_after_retries_exhausted():
    primary = FakeChatModel([RateLimited(), RateLimited(), RateLimited()])
    fallback = FakeChatModel([{"vendor": "gemini"}])
    usage: list[UsageRecord] = []
    c, _ = client(("groq", primary), ("gemini", fallback), max_retries=3)
    c.on_usage = usage.append
    assert c.structured(Out, MSGS).vendor == "gemini"
    assert [u.status for u in usage].count("rate_limited") == 3
    assert usage[-1].provider == "gemini" and usage[-1].status == "ok"


def test_long_retry_after_fails_over_immediately_without_sleeping():
    primary = FakeChatModel([RateLimited(retry_after=600)])
    fallback = FakeChatModel([{"vendor": "g"}])
    c, sleeps = client(("groq", primary), ("gemini", fallback), max_wait=30)
    assert c.structured(Out, MSGS).vendor == "g"
    assert sleeps == []


def test_non_rate_limit_error_skips_retries():
    primary = FakeChatModel([ValueError("boom")])
    fallback = FakeChatModel([{"vendor": "g"}])
    c, sleeps = client(("groq", primary), ("gemini", fallback))
    assert c.structured(Out, MSGS).vendor == "g"
    assert sleeps == [] and len(primary.calls) == 1


def test_all_providers_failing_raises():
    c, _ = client(("a", FakeChatModel([ValueError("x")])), ("b", FakeChatModel([ValueError("y")])))
    with pytest.raises(LLMUnavailable):
        c.structured(Out, MSGS)


def test_cache_prevents_second_call():
    m = FakeChatModel([{"vendor": "once"}])
    c, _ = client(("groq", m))
    c.cache = MemoryCache()
    first = c.structured(Out, MSGS)
    second = c.structured(Out, MSGS)
    assert first == second and len(m.calls) == 1


def test_classify_http_429_like_exception():
    class Resp:
        headers = {"retry-after": "7"}

    class E(Exception):
        status_code = 429
        response = Resp()

    assert classify(E()) == (True, 7.0)
    assert classify(ValueError()) == (False, None)


def test_default_client_skips_providers_without_a_key(monkeypatch, settings):
    settings.LLM_PROVIDER = "groq"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    client = build_default_client()
    assert [p.name for p in client.providers] == ["google_genai"]
    monkeypatch.delenv("GOOGLE_API_KEY")
    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="api_key"):
        build_default_client()
