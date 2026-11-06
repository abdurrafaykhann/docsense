from datetime import timedelta

import pytest
from django.utils import timezone

from apps.llm.models import LLMUsage
from conftest import client_for

pytestmark = pytest.mark.django_db


def add(provider, status, chars=400, latency=1.0, days_ago=0):
    row = LLMUsage.objects.create(provider=provider, schema="InvoiceExtraction", status=status,
                                  prompt_chars=chars, latency_s=latency)  # fmt: skip
    LLMUsage.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=days_ago))


def staff(world):
    u = world["users"]["member"]
    u.is_staff = True
    u.save()
    return client_for(u)


def test_usage_is_aggregated_per_provider_and_day_with_cache_and_429_counts(world):
    add("groq", "ok", 800, 1.0)
    add("groq", "ok", 400, 3.0)
    add("groq", "rate_limited", 400, 0.2)
    add("gemini", "ok", 1200, 2.0)
    add("cache", "cache_hit", 400, 0.0)
    add("groq", "ok", 4000, 1.0, days_ago=40)  # outside the 14-day default window
    data = staff(world).get("/api/v1/admin/llm-usage/").json()
    g = data["providers"]["groq"]
    assert (g["requests"], g["ok"], g["rate_limited"], g["tokens_est"]) == (3, 2, 1, 400)
    assert g["avg_latency_s"] == pytest.approx(1.4, abs=0.01)
    assert data["providers"]["gemini"]["tokens_est"] == 300
    t = data["totals"]
    assert (t["requests"], t["cache_hits"], t["rate_limited"]) == (4, 1, 1)
    assert t["cache_hit_rate"] == 0.2 and t["tokens_est"] == 700
    assert len(data["days"]) == 1 and data["days"][0]["providers"]["groq"]["ok"] == 2
    wide = staff(world).get("/api/v1/admin/llm-usage/?days=90").json()
    assert wide["providers"]["groq"]["requests"] == 4 and len(wide["days"]) == 2


def test_usage_is_staff_only(world):
    for who in ("owner", "member", "viewer"):
        assert client_for(world["users"][who]).get("/api/v1/admin/llm-usage/").status_code == 403
    assert client_for().get("/api/v1/admin/llm-usage/").status_code == 401
    assert client_for(api_key=world["raw_key"]).get("/api/v1/admin/llm-usage/").status_code == 403
