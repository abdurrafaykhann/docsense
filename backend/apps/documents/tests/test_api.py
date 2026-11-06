import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.tests.test_pipeline import GOOD, LINES
from conftest import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    monkeypatch.setattr(services, "get_ocr", lambda: FakeOCR(LINES))
    monkeypatch.setattr(
        services, "get_llm", lambda: LLMClient([Provider("fake", FakeChatModel([GOOD] * 20))])
    )


def png(name="inv.png", ctype="image/png"):
    buf = io.BytesIO()
    Image.new("RGB", (400, 500), "white").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type=ctype)


def url(ws, suffix=""):
    return f"/api/v1/workspaces/{ws.id}/documents/{suffix}"


def test_member_uploads_and_pipeline_completes(world):
    c = client_for(world["users"]["member"])
    res = c.post(url(world["ws"]), {"files": png()}, format="multipart")
    assert res.status_code == 201, res.content
    doc = res.json()["documents"][0]
    assert doc["status"] == "done"  # celery runs eagerly under test settings
    detail = c.get(url(world["ws"], f"{doc['id']}/")).json()
    fields = {f["name"]: f for f in detail["extraction"]["fields"]}
    assert fields["vendor_name"]["value"] == "ACME TRADERS"
    assert fields["total"]["bbox"] is not None
    assert detail["pages"][0]["number"] == 1
    img = c.get(url(world["ws"], f"{doc['id']}/pages/1/image/"))
    assert img.status_code == 200 and img["Content-Type"] == "image/jpeg"


def test_viewer_cannot_upload_but_can_read(world):
    viewer = client_for(world["users"]["viewer"])
    assert viewer.post(url(world["ws"]), {"files": png()}, format="multipart").status_code == 403
    assert viewer.get(url(world["ws"])).status_code == 200


def test_outsider_and_anonymous_blocked(world):
    assert client_for(world["users"]["outsider"]).get(url(world["ws"])).status_code == 404
    assert client_for().get(url(world["ws"])).status_code == 401


def test_cross_workspace_document_not_reachable(world):
    owner = client_for(world["users"]["owner"])
    doc_id = owner.post(url(world["ws"]), {"files": png()}, format="multipart").json()["documents"][
        0
    ]["id"]
    other = client_for(world["users"]["outsider"])
    assert other.get(url(world["other"], f"{doc_id}/")).status_code == 404
    assert other.get(url(world["other"], f"{doc_id}/pages/1/image/")).status_code == 404
    assert other.delete(url(world["other"], f"{doc_id}/")).status_code == 404


def test_api_key_can_upload(world):
    c = client_for(api_key=world["raw_key"])
    res = c.post(url(world["ws"]), {"files": png()}, format="multipart")
    assert res.status_code == 201


def test_rejects_unsupported_type(world):
    c = client_for(world["users"]["member"])
    bad = SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
    res = c.post(url(world["ws"]), {"files": bad}, format="multipart")
    assert res.status_code == 400 and "Unsupported" in res.json()["errors"][0]["error"]


def test_daily_limit_applies_per_file_and_partial_success(world):
    ws = world["ws"]
    ws.daily_upload_limit = 1
    ws.save()
    c = client_for(world["users"]["member"])
    res = c.post(url(ws), {"files": [png("a.png"), png("b.png")]}, format="multipart")
    body = res.json()
    assert res.status_code == 201 and len(body["documents"]) == 1
    assert "limit" in body["errors"][0]["error"].lower()


def test_oversize_file_rejected(world):
    ws = world["ws"]
    ws.max_upload_mb = 0  # anything non-empty is too large
    ws.save()
    res = client_for(world["users"]["member"]).post(url(ws), {"files": png()}, format="multipart")
    assert res.status_code == 400 and "size" in res.json()["errors"][0]["error"].lower()


def test_list_filter_reprocess_and_delete(world):
    c = client_for(world["users"]["member"])
    doc_id = c.post(url(world["ws"]), {"files": png("one.png")}, format="multipart").json()[
        "documents"
    ][0]["id"]
    assert len(c.get(url(world["ws"]) + "?status=done").json()) == 1
    assert c.get(url(world["ws"]) + "?status=failed").json() == []
    assert c.get(url(world["ws"]) + "?q=one").json()[0]["id"] == doc_id
    assert c.post(url(world["ws"], f"{doc_id}/reprocess/")).status_code == 202
    detail = c.get(url(world["ws"], f"{doc_id}/")).json()
    assert detail["extraction"]["version"] == 2
    assert c.delete(url(world["ws"], f"{doc_id}/")).status_code == 204
    assert c.get(url(world["ws"], f"{doc_id}/")).status_code == 404
