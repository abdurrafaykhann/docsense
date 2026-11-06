from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.documents.models import Invoice, InvoiceLineItem, Vendor
from apps.workspaces.views import WorkspaceScoped

from . import service
from .detectors import item_key
from .models import Flag


def _invoices(request, workspace_id):
    qs = Invoice.objects.filter(workspace_id=workspace_id, total__isnull=False)
    for param, lookup in (("date_from", "invoice_date__gte"), ("date_to", "invoice_date__lte")):
        raw = request.query_params.get(param)
        if raw:
            d = parse_date(raw)
            if d is None:
                raise ValidationError({param: "Use YYYY-MM-DD."})
            qs = qs.filter(**{lookup: d})
    return qs


class Spend(WorkspaceScoped):
    def get(self, request, workspace_id):
        group = request.query_params.get("group_by", "month")
        qs = _invoices(request, workspace_id)
        if group == "month":
            rows = (
                qs.exclude(invoice_date=None)
                .annotate(k=TruncMonth("invoice_date"))
                .values("k")
                .annotate(total=Sum("total"), count=Count("id"))
                .order_by("k")
            )
            data = [
                {"key": r["k"].strftime("%Y-%m"), "label": r["k"].strftime("%b %Y"),
                 "total": float(r["total"]), "count": r["count"]}
                for r in rows
            ]  # fmt: skip
        elif group == "vendor":
            rows = (
                qs.values("vendor_id", "vendor__name")
                .annotate(total=Sum("total"), count=Count("id"))
                .order_by("-total")
            )
            data = [
                {"key": str(r["vendor_id"]), "label": r["vendor__name"] or "Unknown vendor",
                 "total": float(r["total"]), "count": r["count"]}
                for r in rows
            ]  # fmt: skip
        elif group == "category":
            rows = (
                qs.values("category")
                .annotate(total=Sum("total"), count=Count("id"))
                .order_by("-total")
            )
            data = [
                {"key": r["category"] or "uncategorized", "label": r["category"] or "uncategorized",
                 "total": float(r["total"]), "count": r["count"]}
                for r in rows
            ]  # fmt: skip
        else:
            raise ValidationError({"group_by": "month, vendor or category."})
        return Response({"group_by": group, "rows": data})


class Summary(WorkspaceScoped):
    def get(self, request, workspace_id):
        qs = _invoices(request, workspace_id)
        agg = qs.aggregate(total=Sum("total"), count=Count("id"))
        open_flags = Flag.objects.filter(workspace_id=workspace_id, resolved=False)
        return Response(
            {
                "invoices": agg["count"],
                "total_spend": float(agg["total"] or 0),
                "average": float(agg["total"] or 0) / agg["count"] if agg["count"] else 0,
                "open_flags": open_flags.count(),
                "vendors": Vendor.objects.filter(workspace_id=workspace_id).count(),
            }
        )


def flag_payload(f: Flag) -> dict:
    return {
        "id": f.id,
        "document_id": f.document_id,
        "document": f.document.original_name,
        "kind": f.kind,
        "severity": f.severity,
        "evidence": f.evidence,
        "resolved": f.resolved,
        "created_at": f.created_at,
    }


class FlagList(WorkspaceScoped):
    def get(self, request, workspace_id):
        qs = Flag.objects.filter(workspace_id=workspace_id).select_related("document")
        if kind := request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        resolved = request.query_params.get("resolved")
        if resolved in ("true", "false"):
            qs = qs.filter(resolved=resolved == "true")
        return Response([flag_payload(f) for f in qs[:200]])


class FlagDetail(WorkspaceScoped):
    def patch(self, request, workspace_id, pk):
        f = get_object_or_404(
            Flag.objects.select_related("document"), pk=pk, workspace_id=workspace_id
        )
        f.resolved = bool(request.data.get("resolved", True))
        f.resolved_by = None if request.auth else request.user
        f.save(update_fields=["resolved", "resolved_by"])
        return Response(flag_payload(f))


class Detect(WorkspaceScoped):
    def post(self, request, workspace_id):
        return Response(service.run_detectors(workspace_id))


class VendorList(WorkspaceScoped):
    def get(self, request, workspace_id):
        rows = (
            Invoice.objects.filter(workspace_id=workspace_id)
            .values("vendor_id", "vendor__name")
            .annotate(total=Sum("total"), count=Count("id"))
            .order_by("-total")
        )
        return Response(
            [{"id": r["vendor_id"], "name": r["vendor__name"], "total": float(r["total"] or 0),
              "count": r["count"]} for r in rows if r["vendor_id"]]
        )  # fmt: skip


class PriceHistory(WorkspaceScoped):
    def get(self, request, workspace_id, pk):
        vendor = get_object_or_404(Vendor, pk=pk, workspace_id=workspace_id)
        series: dict[str, list] = {}
        items = (
            InvoiceLineItem.objects.filter(
                invoice__vendor=vendor, invoice__workspace_id=workspace_id, unit_price__isnull=False
            )
            .select_related("invoice")
            .order_by("invoice__invoice_date", "id")
        )
        for li in items:
            series.setdefault(item_key(li.description), []).append(
                {"date": li.invoice.invoice_date, "unit_price": float(li.unit_price),
                 "document_id": li.invoice.document_id}
            )  # fmt: skip
        return Response(
            {"vendor": vendor.name, "items": [{"item": k, "points": v} for k, v in series.items()]}
        )
