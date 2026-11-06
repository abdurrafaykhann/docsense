"""Provider-agnostic classification of LLM errors (rate limits vs. real failures)."""

from __future__ import annotations


class LLMUnavailable(Exception):
    """All providers failed or are rate limited beyond the allowed wait."""


class RateLimited(Exception):
    """Raised by fakes/adapters; real SDK errors are classified by `classify`."""

    def __init__(self, message: str = "rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_from_headers(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    for key in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        raw = headers.get(key)
        if raw is None:
            continue
        try:
            return float(str(raw).rstrip("s"))
        except ValueError:
            continue
    return None


def classify(exc: Exception) -> tuple[bool, float | None]:
    """Return (is_rate_limit, retry_after_seconds)."""
    if isinstance(exc, RateLimited):
        return True, exc.retry_after
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    name = type(exc).__name__.lower()
    if status == 429 or "ratelimit" in name or "resourceexhausted" in name:
        explicit = getattr(exc, "retry_after", None)
        return True, explicit if explicit is not None else _retry_after_from_headers(exc)
    return False, None
