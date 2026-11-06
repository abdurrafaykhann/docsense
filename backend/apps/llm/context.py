"""Ambient (workspace, document) context so usage rows can be attributed without plumbing."""

from contextlib import contextmanager
from contextvars import ContextVar

_ctx: ContextVar[dict | None] = ContextVar("llm_ctx", default=None)


@contextmanager
def usage_context(**kw):
    token = _ctx.set({**(_ctx.get() or {}), **kw})
    try:
        yield
    finally:
        _ctx.reset(token)


def current() -> dict:
    return _ctx.get() or {}
