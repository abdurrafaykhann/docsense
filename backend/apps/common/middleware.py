"""Public-demo guard (DEMO_READONLY=1).

A hosted demo is shared by every visitor and runs on free-tier LLM keys, so it must not be
writable and must not let strangers burn the quota:

* every write under /api/ is refused (403) except login/refresh and the two "ask" endpoints,
  which are reads in spirit (they only create a conversation row);
* the ask endpoints share a global daily cap (DEMO_ASK_DAILY_CAP) so the free Groq/Gemini
  quota cannot be exhausted by one visitor.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

SAFE = {"GET", "HEAD", "OPTIONS"}
ALLOWED_WRITES = re.compile(r"^/api/v1/auth/(login|refresh)/$")
ASK = re.compile(r"^/api/v1/workspaces/\d+/(chat|agent)/ask/$")


def _refuse(detail: str, status: int = 403) -> JsonResponse:
    return JsonResponse({"detail": detail, "demo_readonly": True}, status=status)


class DemoReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "DEMO_READONLY", False):
            return self.get_response(request)
        path, method = request.path, request.method
        if path.startswith("/api/") and method not in SAFE:
            if ASK.match(path):
                key = f"demo-ask:{timezone.now():%Y%m%d}"
                cache.add(key, 0, 90_000)
                if cache.incr(key) > settings.DEMO_ASK_DAILY_CAP:
                    return _refuse(
                        "The public demo's daily question limit was reached (free LLM quota). "
                        "Try again tomorrow, or run DocSense locally with your own keys.",
                        429,
                    )
            elif not ALLOWED_WRITES.match(path):
                return _refuse(
                    "This public demo is read-only. Uploading, editing and retraining run in the "
                    "full local setup (docker compose up); see the README."
                )
        return self.get_response(request)
