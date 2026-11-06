"""Webhook payloads (what n8n and other receivers see)."""

from __future__ import annotations

from django.conf import settings

from apps.documents.models import Document
from apps.documents.review import effective_invoice


def _link(doc_id: int) -> str:
    base = getattr(settings, "PUBLIC_APP_URL", "http://localhost:5173")
    return f"{base}/#/documents/{doc_id}"


def processed_payload(doc: Document) -> dict:
    ext = doc.extractions.first()
    data: dict = {}
    issues: list[str] = []
    if ext is not None:
        inv = effective_invoice(ext)
        data = {
            "vendor_name": inv.vendor_name, "ntn": inv.ntn, "strn": inv.strn,
            "invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date,
            "currency": inv.currency, "subtotal": inv.subtotal, "tax_rate": inv.tax_rate,
            "sales_tax": inv.sales_tax, "total": inv.total, "line_items_count": len(inv.line_items),
        }  # fmt: skip
        issues = [i["code"] for i in ext.issues]
    return {
        "workspace_id": doc.workspace_id,
        "document": {
            "id": doc.id,
            "name": doc.original_name,
            "status": doc.status,
            "needs_review": doc.status == Document.Status.NEEDS_REVIEW,
            "overall_confidence": ext.overall_confidence if ext else None,
            "url": _link(doc.id),
        },
        "extraction": data,
        "issues": issues,
    }


def flagged_payload(doc: Document, flags: list) -> dict:
    p = processed_payload(doc)
    p["flags"] = [{"kind": f.kind, "severity": f.severity, "evidence": f.evidence} for f in flags]
    return p
