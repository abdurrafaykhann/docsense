"""Human review: apply corrections, re-validate, approve into query-friendly tables."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.validation import rules
from apps.validation.schema import SCALAR_FIELDS, InvoiceExtraction, LineItem, to_number

from .models import AuditEvent, Extraction, FieldValue, Invoice, InvoiceLineItem, Vendor


def effective_invoice(ext: Extraction) -> InvoiceExtraction:
    """Model output overlaid with human corrections."""
    data = dict(ext.data)
    for f in ext.fields.all():
        if f.name in SCALAR_FIELDS and f.reviewed_value is not None:
            data[f.name] = f.reviewed_value if f.reviewed_value != "" else None
    return InvoiceExtraction.model_validate(data)


def revalidate(ext: Extraction) -> list[dict]:
    ext.issues = [i.as_dict() for i in rules.validate(effective_invoice(ext))]
    ext.save(update_fields=["issues"])
    return ext.issues


def audit(document, user, action: str, **detail) -> None:
    AuditEvent.objects.create(document=document, user=user, action=action, detail=detail)


@transaction.atomic
def edit_field(ext: Extraction, name: str, user, *, value=None, bbox=None, page=None) -> FieldValue:
    f = ext.fields.get(name=name)
    before = f.reviewed_value if f.reviewed_value is not None else f.value
    if value is not None:
        f.reviewed_value = str(value).strip()
        f.reviewed_by = user
        f.reviewed_at = timezone.now()
        audit(ext.document, user, "field_edited", field=name, before=before, after=f.reviewed_value)
    if bbox is not None:
        x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in bbox)
        f.bbox = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        f.page = page or f.page or 1
        f.box_edited = True
        f.reviewed_by = user
        f.reviewed_at = timezone.now()
        audit(ext.document, user, "box_edited", field=name, bbox=f.bbox)
    f.save()
    revalidate(ext)
    return f


@transaction.atomic
def edit_line_items(ext: Extraction, items: list[dict], user) -> None:
    parsed = [LineItem.model_validate(i).model_dump(mode="json") for i in items]
    before = len(ext.data.get("line_items", []))
    ext.data = {**ext.data, "line_items": parsed}
    ext.save(update_fields=["data"])
    f = ext.fields.get(name="line_items")
    f.value = f"{len(parsed)} items"
    f.reviewed_value = f.value
    f.reviewed_by = user
    f.reviewed_at = timezone.now()
    f.save()
    audit(ext.document, user, "field_edited", field="line_items", before=before, after=len(parsed))
    revalidate(ext)


def _dec(v) -> Decimal | None:
    n = to_number(v)
    if n is None:
        return None
    try:
        return Decimal(str(n))
    except InvalidOperation:
        return None


@transaction.atomic
def approve(ext: Extraction, user) -> Invoice:
    """Mark reviewed and upsert the denormalised Invoice / LineItems / Vendor."""
    doc = ext.document
    inv = effective_invoice(ext)
    vendor = None
    if inv.vendor_name:
        vendor, _ = Vendor.objects.get_or_create(
            workspace=doc.workspace, name=inv.vendor_name.strip(), defaults={"ntn": inv.ntn or ""}
        )
    parsed_date = rules.parse_iso_date(inv.invoice_date) if inv.invoice_date else None
    invoice, _ = Invoice.objects.update_or_create(
        document=doc,
        defaults={
            "workspace": doc.workspace,
            "vendor": vendor,
            "ntn": inv.ntn or "",
            "strn": inv.strn or "",
            "invoice_number": inv.invoice_number or "",
            "invoice_date": parsed_date,
            "currency": inv.currency,
            "subtotal": _dec(inv.subtotal),
            "tax_rate": _dec(inv.tax_rate),
            "sales_tax": _dec(inv.sales_tax),
            "total": _dec(inv.total),
        },
    )
    invoice.items.all().delete()
    InvoiceLineItem.objects.bulk_create(
        InvoiceLineItem(
            invoice=invoice,
            position=i,
            description=(li.description or "")[:300],
            quantity=_dec(li.quantity),
            unit_price=_dec(li.unit_price),
            amount=_dec(li.amount),
        )
        for i, li in enumerate(inv.line_items)
    )
    ext.needs_review = False
    ext.save(update_fields=["needs_review"])
    doc.status = doc.Status.DONE
    doc.save(update_fields=["status", "updated_at"])
    audit(doc, user, "approved", unresolved=[i["code"] for i in ext.issues])
    return invoice
