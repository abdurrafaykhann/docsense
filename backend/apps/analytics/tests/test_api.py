import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.analytics import service
from apps.analytics.categorize import categorize
from apps.analytics.models import Flag
from apps.documents.models import Document, Invoice, InvoiceLineItem, Vendor
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services as pipeline_services
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.tests.test_pipeline import GOOD, LINES
from conftest import client_for

pytestmark = pytest.mark.django_db
D0 = date(2025, 1, 10)


def make_invoice(ws, vendor, n, total, d, number="", category="grocery", unit_price=None, sha=None):
    doc = Document(
        workspace=ws,
        original_name=f"inv{n}.png",
        content_type="image/png",
        size=1,
        sha256=sha or f"sha{n}-{ws.id}",
        status="done",
    )
    doc.file.save(f"inv{n}.png", ContentFile(b"x"), save=True)
    inv = Invoice.objects.create(
        document=doc,
        workspace=ws,
        vendor=vendor,
        invoice_number=number or f"N{n}",
        invoice_date=d,
        subtotal=Decimal(total) / Decimal("1.18"),
        sales_tax=Decimal(total) * Decimal("0.18") / Decimal("1.18"),
        total=Decimal(total),
        category=category,
    )
    if unit_price is not None:
        InvoiceLineItem.objects.create(
            invoice=inv,
            description="Cooking Oil 1L",
            quantity=1,
            unit_price=unit_price,
            amount=unit_price,
        )
    return inv


@pytest.fixture
def data(world):
    ws = world["ws"]
    a = Vendor.objects.create(workspace=ws, name="Al-Mart")
    b = Vendor.objects.create(workspace=ws, name="Noor Pharmacy")
    for i in range(8):  # Al-Mart: steady ~1180 monthly + rising oil price
        make_invoice(
            ws,
            a,
            i,
            1180 + i * 10,
            D0 + timedelta(days=31 * i),
            unit_price=[520, 525, 530, 528, 532, 531, 529, 700][i],
        )
    make_invoice(ws, b, 20, 590, D0, category="pharmacy")
    return world


def url(ws, suffix):
    return f"/api/v1/workspaces/{ws.id}/analytics/{suffix}"


def test_spend_by_month_vendor_and_category(data):
    c = client_for(data["users"]["viewer"])
    ws = data["ws"]
    months = c.get(url(ws, "spend/?group_by=month")).json()["rows"]
    assert months[0]["key"] == "2025-01" and months[0]["total"] == 1180 + 590
    assert [m["key"] for m in months] == sorted(m["key"] for m in months)
    vendors = c.get(url(ws, "spend/?group_by=vendor")).json()["rows"]
    assert vendors[0]["label"] == "Al-Mart" and vendors[0]["count"] == 8
    cats = {
        r["label"]: r["total"] for r in c.get(url(ws, "spend/?group_by=category")).json()["rows"]
    }
    assert cats["pharmacy"] == 590
    ranged = c.get(url(ws, "spend/?group_by=vendor&date_from=2025-03-01")).json()["rows"]
    assert sum(r["count"] for r in ranged) < 9
    assert c.get(url(ws, "spend/?group_by=colour")).status_code == 400
    assert c.get(url(ws, "spend/?date_from=nope")).status_code == 400


def test_summary_counts(data):
    s = client_for(data["users"]["member"]).get(url(data["ws"], "summary/")).json()
    assert s["invoices"] == 9 and s["vendors"] == 2 and s["total_spend"] > 9000


def test_detect_finds_price_creep_and_is_idempotent(data):
    owner = client_for(data["users"]["member"])
    first = owner.post(url(data["ws"], "detect/")).json()
    assert first["created"] >= 1
    flags = owner.get(url(data["ws"], "flags/")).json()
    creep = [f for f in flags if f["kind"] == "price_creep"]
    assert len(creep) == 1 and creep[0]["evidence"]["increase_pct"] > 30
    assert creep[0]["severity"] == "high" and creep[0]["document"] == "inv7.png"
    again = owner.post(url(data["ws"], "detect/")).json()
    assert again["created"] == 0 and Flag.objects.filter(kind="price_creep").count() == 1


def test_resolved_flags_stay_resolved_and_stale_open_flags_disappear(data):
    c = client_for(data["users"]["member"])
    ws = data["ws"]
    c.post(url(ws, "detect/"))
    flag = Flag.objects.get(kind="price_creep")
    res = c.patch(url(ws, f"flags/{flag.id}/"), {"resolved": True}, format="json")
    assert res.json()["resolved"] is True
    c.post(url(ws, "detect/"))
    assert Flag.objects.get(pk=flag.pk).resolved is True
    # remove the cause: the unresolved flag would vanish, a resolved one is kept as history
    other = Flag.objects.create(workspace=ws, document=Document.objects.first(), kind="near_dup")
    c.post(url(ws, "detect/"))
    assert not Flag.objects.filter(pk=other.pk).exists()
    assert Flag.objects.filter(pk=flag.pk).exists()
    assert c.get(url(ws, "flags/?resolved=false")).json() == [] or all(
        not f["resolved"] for f in c.get(url(ws, "flags/?resolved=false")).json()
    )


def test_exact_duplicate_upload_is_flagged_on_approval(world, monkeypatch):
    monkeypatch.setattr(pipeline_services, "get_ocr", lambda: FakeOCR(LINES))
    monkeypatch.setattr(
        pipeline_services,
        "get_llm",
        lambda: LLMClient([Provider("f", FakeChatModel([GOOD] * 10))]),
    )
    c = client_for(world["users"]["member"])
    ws = world["ws"]
    ids = []
    for _ in range(2):  # same bytes twice: identical sha256, same invoice number
        buf = io.BytesIO()
        Image.new("RGB", (300, 400), "white").save(buf, "PNG")
        f = SimpleUploadedFile("inv.png", buf.getvalue(), content_type="image/png")
        res = c.post(f"/api/v1/workspaces/{ws.id}/documents/", {"files": f}, format="multipart")
        ids.append(res.json()["documents"][0]["id"])
    for i in ids:
        assert c.post(f"/api/v1/workspaces/{ws.id}/documents/{i}/approve/").status_code == 200
    flags = c.get(url(ws, "flags/")).json()
    dup = next(f for f in flags if f["kind"] == "exact_dup")
    assert dup["document_id"] == ids[1] and dup["evidence"]["duplicate_of"] == ids[0]
    assert Invoice.objects.get(document_id=ids[0]).category == "uncategorized"
    assert Document.objects.get(pk=ids[0]).phash  # perceptual hash stored for image-dup checks


def test_price_history_series(data):
    c = client_for(data["users"]["viewer"])
    vid = Vendor.objects.get(name="Al-Mart").id
    hist = c.get(url(data["ws"], f"vendors/{vid}/price-history/")).json()
    pts = hist["items"][0]["points"]
    assert hist["items"][0]["item"] == "cooking oil 1l" and pts[-1]["unit_price"] == 700
    assert [p["date"] for p in pts] == sorted(p["date"] for p in pts)
    vendors = c.get(url(data["ws"], "vendors/")).json()
    assert vendors[0]["name"] == "Al-Mart"


def test_access_control_and_tenant_isolation(data):
    ws, other = data["ws"], data["other"]
    for suffix in ("spend/", "summary/", "flags/", "vendors/"):
        assert client_for(data["users"]["outsider"]).get(url(ws, suffix)).status_code == 404
        assert client_for().get(url(ws, suffix)).status_code == 401
    vendor = Vendor.objects.get(name="Al-Mart")
    out = client_for(data["users"]["outsider"])
    assert out.get(url(other, f"vendors/{vendor.id}/price-history/")).status_code == 404
    assert client_for(data["users"]["viewer"]).post(url(ws, "detect/")).status_code == 403
    assert out.get(url(other, "spend/")).json()["rows"] == []  # sees only its own (empty) data


def test_categorize_keywords():
    assert categorize(["Basmati Rice 5kg", "Sugar 1kg"]) == "grocery"
    assert categorize(["IT Support (hours)", "Printing"]) == "services"
    assert categorize(["Mystery gadget"]) == "uncategorized"
    assert service.compute_specs(0) == []
