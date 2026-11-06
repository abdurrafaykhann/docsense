"""Load approved invoices, run the detectors, persist Flags."""

from __future__ import annotations

import logging

from django.db import transaction

from apps.documents.models import Invoice, InvoiceLineItem

from . import detectors as d
from .models import Flag

log = logging.getLogger(__name__)


def load_rows(workspace_id: int) -> tuple[list[d.InvoiceRow], list[d.ItemRow]]:
    invoices = list(
        Invoice.objects.filter(workspace_id=workspace_id).select_related("document", "vendor")
    )
    n_items = {i.id: 0 for i in invoices}
    items: list[d.ItemRow] = []
    by_id = {i.id: i for i in invoices}
    for li in InvoiceLineItem.objects.filter(invoice_id__in=n_items).order_by("invoice_id"):
        n_items[li.invoice_id] += 1
        inv = by_id[li.invoice_id]
        unit = float(li.unit_price) if li.unit_price is not None else None
        items.append(
            d.ItemRow(inv.document_id, inv.vendor_id, li.description, inv.invoice_date, unit)
        )
    rows = [
        d.InvoiceRow(
            document_id=i.document_id,
            vendor_id=i.vendor_id,
            number=i.invoice_number,
            date=i.invoice_date,
            total=float(i.total) if i.total is not None else None,
            subtotal=float(i.subtotal) if i.subtotal is not None else None,
            sales_tax=float(i.sales_tax) if i.sales_tax is not None else None,
            n_items=n_items[i.id],
            sha256=i.document.sha256,
            phash=i.document.phash,
        )
        for i in invoices
    ]
    return rows, items


def compute_specs(workspace_id: int) -> list[d.FlagSpec]:
    rows, items = load_rows(workspace_id)
    outliers = d.merge_outliers(d.robust_outliers(rows), d.isolation_outliers(rows))
    return [*d.find_duplicates(rows), *outliers, *d.price_creep(items)]


@transaction.atomic
def run_detectors(workspace_id: int) -> dict:
    """Recompute flags. Human decisions survive: resolved flags are never reopened, and stale
    unresolved flags (no longer produced) are removed."""
    specs = compute_specs(workspace_id)
    existing = {(f.document_id, f.kind): f for f in Flag.objects.filter(workspace_id=workspace_id)}
    keep = set()
    created = 0
    new_flags: list[Flag] = []
    for s in specs:
        key = (s.document_id, s.kind)
        keep.add(key)
        flag = existing.get(key)
        if flag is not None:
            if not flag.resolved:
                flag.severity, flag.evidence = s.severity, s.evidence
                flag.save(update_fields=["severity", "evidence"])
            continue
        new_flags.append(
            Flag.objects.create(
                workspace_id=workspace_id,
                document_id=s.document_id,
                kind=s.kind,
                severity=s.severity,
                evidence=s.evidence,
            )
        )
        created += 1
    stale = [f.id for k, f in existing.items() if k not in keep and not f.resolved]
    Flag.objects.filter(id__in=stale).delete()
    _announce(new_flags)
    return {"flags": len(specs), "created": created, "removed": len(stale)}


def run_quietly(workspace_id: int) -> None:
    try:
        run_detectors(workspace_id)
    except Exception:  # noqa: BLE001 - never block an approval
        log.exception("anomaly detection failed for workspace %s", workspace_id)


def _announce(new_flags: list[Flag]) -> None:
    """One `document.flagged` webhook per document that just got new flags."""
    from apps.integrations.payloads import flagged_payload
    from apps.integrations.webhooks import emit_quietly

    by_doc: dict[int, list[Flag]] = {}
    for f in new_flags:
        by_doc.setdefault(f.document_id, []).append(f)
    for flags in by_doc.values():
        doc = flags[0].document
        emit_quietly(doc.workspace_id, "document.flagged", flagged_payload(doc, flags))
