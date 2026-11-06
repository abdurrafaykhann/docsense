import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.documents.models import AuditEvent, Invoice, Vendor
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.tests.test_pipeline import GOOD, LINES
from conftest import client_for

pytestmark = pytest.mark.django_db
BAD = {**GOOD, "total": 3500}  # arithmetic error -> needs_review


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    monkeypatch.setattr(services, "get_ocr", lambda: FakeOCR(LINES))
    monkeypatch.setattr(
        services, "get_llm", lambda: LLMClient([Provider("fake", FakeChatModel([BAD] * 20))])
    )


def upload(client, ws, name="inv.png"):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "PNG")
    f = SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")
    res = client.post(f"/api/v1/workspaces/{ws.id}/documents/", {"files": f}, format="multipart")
    return res.json()["documents"][0]["id"]


def u(ws, doc, suffix=""):
    return f"/api/v1/workspaces/{ws.id}/documents/{doc}/{suffix}"


@pytest.fixture
def flagged(world):
    c = client_for(world["users"]["member"])
    return c, upload(c, world["ws"])


def test_flagged_doc_is_in_queue(world, flagged):
    c, doc = flagged
    q = c.get(f"/api/v1/workspaces/{world['ws'].id}/review/queue/").json()
    assert q["count"] == 1 and q["documents"][0]["id"] == doc


def test_correcting_total_clears_issue_and_records_audit(world, flagged):
    c, doc = flagged
    ws = world["ws"]
    before = c.get(u(ws, doc)).json()["extraction"]
    assert any(i["code"] == "total_mismatch" for i in before["issues"])
    res = c.patch(u(ws, doc, "fields/total/"), {"value": "3540"}, format="json")
    assert res.status_code == 200
    ext = res.json()
    assert not any(i["code"] == "total_mismatch" for i in ext["issues"])
    total = next(f for f in ext["fields"] if f["name"] == "total")
    assert total["reviewed_value"] == "3540" and total["reviewed"] and total["value"] == "3500"
    ev = AuditEvent.objects.get(action="field_edited")
    assert ev.detail == {"field": "total", "before": "3500", "after": "3540"}
    assert ev.user == world["users"]["member"]


def test_wrong_correction_keeps_issue(world, flagged):
    c, doc = flagged
    res = c.patch(u(world["ws"], doc, "fields/total/"), {"value": "9999"}, format="json")
    assert any(i["code"] == "total_mismatch" for i in res.json()["issues"])


def test_box_correction_is_clamped_and_ordered(world, flagged):
    c, doc = flagged
    res = c.patch(
        u(world["ws"], doc, "fields/total/"),
        {"bbox": [0.9, 0.95, 0.5, 1.4], "page": 1},
        format="json",
    )
    f = next(f for f in res.json()["fields"] if f["name"] == "total")
    assert f["bbox"] == [0.5, 0.95, 0.9, 1.0] and f["box_edited"] is True
    assert AuditEvent.objects.filter(action="box_edited").count() == 1


def test_edit_validation_errors(world, flagged):
    c, doc = flagged
    ws = world["ws"]
    assert c.patch(u(ws, doc, "fields/nope/"), {"value": "x"}, format="json").status_code == 400
    assert c.patch(u(ws, doc, "fields/total/"), {}, format="json").status_code == 400
    assert c.patch(u(ws, doc, "fields/total/"), {"bbox": [1, 2]}, format="json").status_code == 400


def test_line_item_edit_revalidates(world, flagged):
    c, doc = flagged
    ws = world["ws"]
    items = [{"description": "Widget", "quantity": 2, "unit_price": 500, "amount": 900}]
    res = c.put(u(ws, doc, "line-items/"), {"line_items": items}, format="json")
    codes = {i["code"] for i in res.json()["issues"]}
    assert {"line_math", "subtotal_mismatch"} <= codes
    assert res.json()["line_items"][0]["amount"] == 900


def test_approve_writes_invoice_vendor_and_items(world, flagged):
    c, doc = flagged
    ws = world["ws"]
    c.patch(u(ws, doc, "fields/total/"), {"value": "3,540.00"}, format="json")
    res = c.post(u(ws, doc, "approve/"))
    assert res.status_code == 200 and res.json()["status"] == "done"
    inv = Invoice.objects.get(document_id=doc)
    assert inv.total == Decimal("3540.00") and inv.subtotal == Decimal("3000.00")
    assert str(inv.invoice_date) == "2024-03-12" and inv.invoice_number == "INV-0042"
    assert inv.vendor.name == "ACME TRADERS" and Vendor.objects.count() == 1
    assert [i.amount for i in inv.items.all()] == [Decimal("1000.00"), Decimal("2000.00")]
    assert c.get(f"/api/v1/workspaces/{ws.id}/review/queue/").json()["count"] == 0
    assert c.get(u(ws, doc)).json()["audit"][0]["action"] == "approved"


def test_reapproval_updates_instead_of_duplicating(world, flagged):
    c, doc = flagged
    ws = world["ws"]
    c.post(u(ws, doc, "approve/"))
    c.patch(u(ws, doc, "fields/total/"), {"value": "3541"}, format="json")
    c.post(u(ws, doc, "approve/"))
    assert Invoice.objects.filter(document_id=doc).count() == 1
    assert Invoice.objects.get(document_id=doc).total == Decimal("3541.00")


def test_viewer_cannot_edit_or_approve_outsider_gets_404(world, flagged):
    _, doc = flagged
    ws = world["ws"]
    viewer = client_for(world["users"]["viewer"])
    assert (
        viewer.patch(u(ws, doc, "fields/total/"), {"value": "1"}, format="json").status_code == 403
    )
    assert viewer.post(u(ws, doc, "approve/")).status_code == 403
    assert (
        viewer.put(u(ws, doc, "line-items/"), {"line_items": []}, format="json").status_code == 403
    )
    out = client_for(world["users"]["outsider"])
    assert out.post(u(ws, doc, "approve/")).status_code == 404
    assert Invoice.objects.count() == 0


def test_cross_workspace_ids_do_not_leak(world, flagged):
    _, doc = flagged
    other = client_for(world["users"]["outsider"])
    url = f"/api/v1/workspaces/{world['other'].id}/documents/{doc}/approve/"
    assert other.post(url).status_code == 404


def test_api_key_edits_recorded_without_user(world, flagged):
    _, doc = flagged
    key = client_for(api_key=world["raw_key"])
    res = key.patch(u(world["ws"], doc, "fields/total/"), {"value": "3540"}, format="json")
    assert res.status_code == 200
    assert AuditEvent.objects.get(action="field_edited").user is None


def test_queue_orders_least_confident_first(world, monkeypatch):
    c = client_for(world["users"]["member"])
    first = upload(c, world["ws"], "a.png")
    # second doc: hallucinated vendor -> lower confidence
    worse = {**BAD, "vendor_name": "Phantom Corp"}
    monkeypatch.setattr(
        services, "get_llm", lambda: LLMClient([Provider("fake", FakeChatModel([worse] * 5))])
    )
    second = upload(c, world["ws"], "b.png")
    q = c.get(f"/api/v1/workspaces/{world['ws'].id}/review/queue/").json()["documents"]
    assert [d["id"] for d in q] == [second, first]
