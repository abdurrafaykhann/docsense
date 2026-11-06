from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.learning.views import IsStaffUser

from .models import LLMUsage


class UsageStats(APIView):
    """Free-tier accounting: requests, 429s, cache hits and estimated tokens per provider/day."""

    permission_classes = [IsStaffUser]

    def get(self, request):
        days = max(1, min(int(request.query_params.get("days", 14)), 90))
        since = timezone.now() - timedelta(days=days)
        qs = LLMUsage.objects.filter(created_at__gte=since)
        rows = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day", "provider", "status")
            .annotate(n=Count("id"), chars=Sum("prompt_chars"), latency=Avg("latency_s"))
            .order_by("day")
        )
        by_day: dict[str, dict] = {}
        by_provider: dict[str, dict] = {}
        for r in rows:
            p = by_day.setdefault(r["day"].isoformat(), {}).setdefault(
                r["provider"],
                {"ok": 0, "rate_limited": 0, "error": 0, "cache_hit": 0, "tokens_est": 0},
            )
            p[r["status"]] = p.get(r["status"], 0) + r["n"]
            if r["status"] != "cache_hit":
                p["tokens_est"] += (r["chars"] or 0) // 4
            t = by_provider.setdefault(
                r["provider"],
                {
                    "requests": 0,
                    "ok": 0,
                    "rate_limited": 0,
                    "error": 0,
                    "tokens_est": 0,
                    "_lat": [],
                },
            )
            if r["status"] != "cache_hit":
                t["requests"] += r["n"]
                t["tokens_est"] += (r["chars"] or 0) // 4
                t["_lat"].append(((r["latency"] or 0), r["n"]))
            t[r["status"]] = t.get(r["status"], 0) + r["n"]
        providers = {}
        for name, t in by_provider.items():
            lat = t.pop("_lat")
            total_n = sum(n for _, n in lat)
            t["avg_latency_s"] = round(sum(v * n for v, n in lat) / total_n, 2) if total_n else 0
            providers[name] = t
        hits = qs.filter(status="cache_hit").count()
        calls = qs.exclude(status="cache_hit").count()
        return Response(
            {
                "days": [{"day": d, "providers": p} for d, p in sorted(by_day.items())],
                "providers": providers,
                "totals": {
                    "requests": calls,
                    "cache_hits": hits,
                    "cache_hit_rate": round(hits / (hits + calls), 3) if hits + calls else 0,
                    "rate_limited": qs.filter(status="rate_limited").count(),
                    "tokens_est": sum(p["tokens_est"] for p in providers.values()),
                },
            }
        )
