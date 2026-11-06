import io
import json
import time

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.documents.models import Invoice
from apps.integrations import webhooks
from apps.integrations.models import WebhookDelivery, WebhookEndpoint
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services as pipeline_services
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.tests.test_pipeline import GOOD, LINES
from conftest import client_for

pytestmark = pytest.mark.django_db
PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731 - a public IP


@pytest.fixture(autouse=True)
def allow_private(settings, monkeypatch):
    settings.WEBHOOKS_ALLOW_PRIVATE = True  # most tests use fake senders; SSRF tests turn it off


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(pipeline_services, "get_ocr", lambda: FakeOCR(LINES))
    monkeypatch.setattr(
        pipeline_services, "get_llm",
        lambda: LLMClient([Provider("f", FakeChatModel([{**GOOD, "total": 3500}] * 20))]),
    )  # fmt: skip


def png(name="inv.png"):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


# ------------------------------------------------------------------ signing
def test_signature_roundtrip_tamper_and_replay_protection():
    body = b'{"event":"ping"}'
    ts = str(int(time.time()))
    sig = webhooks.sign("whsec_x", ts, body)
    assert sig.startswith("sha256=") and webhooks.verify("whsec_x", ts, body, sig)
    assert not webhooks.verify("whsec_x", ts, b'{"event":"pong"}', sig)  # body tampered
    assert not webhooks.verify("whsec_other", ts, body, sig)  # wrong secret
    old = str(int(time.time()) - 3600)
    assert not webhooks.verify("whsec_x", old, body, webhooks.sign("whsec_x", old, body))  # replay


# ------------------------------------------------------------------ SSRF guard
def test_ssrf_guard_blocks_private_ranges_and_plain_http(settings):
    settings.WEBHOOKS_ALLOW_PRIVATE = False
    ok, _ = webhooks.is_safe_url("https://hooks.example.com/x", resolver=PUBLIC)
    assert ok
    for addr in ("127.0.0.1", "10.0.0.5", "192.168.1.9", "169.254.169.254", "::1"):
        ok, why = webhooks.is_safe_url("https://evil.example.com/x", resolver=lambda h, a=addr: [a])
        assert not ok and "non-public" in why, addr
    assert webhooks.is_safe_url("http://hooks.example.com/x", resolver=PUBLIC)[0] is False
    assert webhooks.is_safe_url("ftp://hooks.example.com/x", resolver=PUBLIC)[0] is False
    assert (
        webhooks.is_safe_url(
            "https://nope.invalid", resolver=lambda h: (_ for _ in ()).throw(OSError())
        )[0]
        is False
    )


# ------------------------------------------------------------------ CRUD + permissions
def hooks_url(ws, suffix=""):
    return f"/api/v1/workspaces/{ws.id}/webhooks/{suffix}"


def test_owner_creates_webhook_secret_shown_once_and_validates_input(world):
    owner = client_for(world["users"]["owner"])
    res = owner.post(
        hooks_url(world["ws"]),
        {"url": "https://x.example.com/h", "events": ["document.processed"]},
        format="json",
    )
    assert res.status_code == 201 and res.json()["secret"].startswith("whsec_")
    assert "secret" not in owner.get(hooks_url(world["ws"])).json()[0]
    assert (
        owner.post(
            hooks_url(world["ws"]),
            {"url": "https://x.example.com", "events": ["bogus"]},
            format="json",
        ).status_code
        == 400
    )
    assert (
        owner.post(hooks_url(world["ws"]), {"url": "not-a-url"}, format="json").status_code == 400
    )


def test_private_urls_rejected_when_guard_is_on(world, settings, monkeypatch):
    settings.WEBHOOKS_ALLOW_PRIVATE = False
    monkeypatch.setattr(webhooks, "default_resolver", lambda h: ["127.0.0.1"])
    owner = client_for(world["users"]["owner"])
    res = owner.post(hooks_url(world["ws"]), {"url": "https://localhost/h"}, format="json")
    assert res.status_code == 400 and "non-public" in str(res.json())


def test_webhook_management_is_owner_only_and_tenant_isolated(world):
    ws = world["ws"]
    ep = WebhookEndpoint.objects.create(
        workspace=ws, url="https://x.example.com/h", secret="whsec_a"
    )
    for who in ("member", "viewer"):
        c = client_for(world["users"][who])
        assert c.get(hooks_url(ws)).status_code == 403
        assert (
            c.post(hooks_url(ws), {"url": "https://x.example.com"}, format="json").status_code
            == 403
        )
        assert c.delete(hooks_url(ws, f"{ep.id}/")).status_code == 403
    assert client_for(api_key=world["raw_key"]).get(hooks_url(ws)).status_code == 403
    out = client_for(world["users"]["outsider"])
    assert out.get(hooks_url(ws)).status_code == 404
    assert (
        out.delete(hooks_url(world["other"], f"{ep.id}/")).status_code == 404
    )  # id from another workspace
    assert client_for(world["users"]["owner"]).delete(hooks_url(ws, f"{ep.id}/")).status_code == 204


# ------------------------------------------------------------------ delivery + retries
def make_delivery(world, url="https://x.example.com/h"):
    ep = WebhookEndpoint.objects.create(workspace=world["ws"], url=url, secret="whsec_s")
    return WebhookDelivery.objects.create(
        endpoint=ep, event="ping", payload={"event": "ping", "a": 1}
    )


def test_successful_delivery_sends_verifiable_headers(world):
    d = make_delivery(world)
    seen = {}

    def sender(url, body, headers):
        seen.update(url=url, body=body, headers=headers)
        return 200, "ok"

    assert webhooks.attempt_delivery(d, sender=sender, resolver=PUBLIC)
    d.refresh_from_db()
    assert d.status == "delivered" and d.attempts == 1 and d.response_code == 200
    h = seen["headers"]
    assert h["X-DocSense-Event"] == "ping" and h["X-DocSense-Delivery"] == str(d.id)
    assert webhooks.verify(
        "whsec_s", h["X-DocSense-Timestamp"], seen["body"], h["X-DocSense-Signature"]
    )
    assert json.loads(seen["body"]) == {"event": "ping", "a": 1}


def test_failures_stay_pending_until_the_last_attempt_then_fail(world):
    d = make_delivery(world)
    boom = lambda *a: (500, "server error")  # noqa: E731
    for expected in ("pending", "pending", "failed"):
        webhooks.attempt_delivery(d, sender=boom, resolver=PUBLIC)
        d.refresh_from_db()
        assert d.status == expected
    assert d.attempts == webhooks.MAX_ATTEMPTS and "HTTP 500" in d.error

    d2 = make_delivery(world)

    def raises(*a):
        raise ConnectionError("refused")

    webhooks.attempt_delivery(d2, sender=raises, resolver=PUBLIC)
    d2.refresh_from_db()
    assert "ConnectionError" in d2.error and d2.response_code is None


def test_celery_task_retries_until_delivered(world, monkeypatch):
    from apps.integrations import tasks

    d = make_delivery(world)
    calls = []

    def flaky(url, body, headers):
        calls.append(1)
        return (200, "ok") if len(calls) == 3 else (503, "later")

    monkeypatch.setattr(webhooks, "http_sender", flaky)
    monkeypatch.setattr(
        webhooks.attempt_delivery, "__defaults__", (flaky, webhooks.default_resolver)
    )
    tasks.deliver.delay(d.id)  # eager: retries run inline
    d.refresh_from_db()
    assert d.status == "delivered" and d.attempts == 3


def test_test_endpoint_sends_a_ping(world, monkeypatch):
    monkeypatch.setattr(
        webhooks.attempt_delivery,
        "__defaults__",
        (lambda *a: (200, "ok"), webhooks.default_resolver),
    )
    ep = WebhookEndpoint.objects.create(
        workspace=world["ws"], url="https://x.example.com/h", secret="s"
    )
    res = client_for(world["users"]["owner"]).post(hooks_url(world["ws"], f"{ep.id}/test/"))
    assert (
        res.status_code == 202
        and res.json()["event"] == "ping"
        and res.json()["status"] == "delivered"
    )
    log = (
        client_for(world["users"]["owner"])
        .get(hooks_url(world["ws"], f"{ep.id}/deliveries/"))
        .json()
    )
    assert log[0]["status"] == "delivered"


# ------------------------------------------------------------------ events from the product
def test_pipeline_emits_document_processed_to_subscribed_endpoints_only(
    world, pipeline, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        webhooks.attempt_delivery,
        "__defaults__",
        (
            lambda url, body, h: sent.append((url, json.loads(body))) or (200, "ok"),
            webhooks.default_resolver,
        ),
    )
    ws = world["ws"]
    WebhookEndpoint.objects.create(
        workspace=ws, url="https://a.example.com/h", secret="s", events=["document.processed"]
    )
    WebhookEndpoint.objects.create(
        workspace=ws, url="https://b.example.com/h", secret="s", events=["document.flagged"]
    )
    WebhookEndpoint.objects.create(
        workspace=ws, url="https://off.example.com/h", secret="s", active=False
    )
    WebhookEndpoint.objects.create(
        workspace=world["other"], url="https://other.example.com/h", secret="s"
    )
    c = client_for(world["users"]["member"])
    c.post(f"/api/v1/workspaces/{ws.id}/documents/", {"files": png()}, format="multipart")
    assert [u for u, _ in sent] == ["https://a.example.com/h"]
    payload = sent[0][1]
    assert payload["event"] == "document.processed" and payload["workspace_id"] == ws.id
    assert payload["document"]["needs_review"] is True  # total 3500 breaks the arithmetic
    assert (
        payload["extraction"]["vendor_name"] == "ACME TRADERS"
        and "total_mismatch" in payload["issues"]
    )


def test_flagged_event_fires_once_for_a_new_duplicate(world, pipeline, monkeypatch):
    sent = []
    monkeypatch.setattr(
        webhooks.attempt_delivery,
        "__defaults__",
        (
            lambda url, body, h: sent.append(json.loads(body)) or (200, "ok"),
            webhooks.default_resolver,
        ),
    )
    ws = world["ws"]
    WebhookEndpoint.objects.create(
        workspace=ws, url="https://a.example.com/h", secret="s", events=["document.flagged"]
    )
    c = client_for(world["users"]["member"])
    ids = []
    for _ in range(2):  # same bytes + same invoice number twice
        res = c.post(f"/api/v1/workspaces/{ws.id}/documents/", {"files": png()}, format="multipart")
        ids.append(res.json()["documents"][0]["id"])
    for i in ids:
        c.post(f"/api/v1/workspaces/{ws.id}/documents/{i}/approve/")
    assert len(sent) == 1
    assert sent[0]["event"] == "document.flagged" and sent[0]["document"]["id"] == ids[1]
    assert sent[0]["flags"][0]["kind"] == "exact_dup"
    assert Invoice.objects.count() == 2


# ------------------------------------------------------------------ inbound (n8n -> DocSense)
def test_inbound_uses_the_api_key_workspace_and_exposes_a_status_endpoint(world, pipeline):
    key = client_for(api_key=world["raw_key"])
    res = key.post(
        "/api/v1/integrations/inbound/",
        {"files": png(), "source": "n8n", "sender": "a@b.pk", "subject": "Invoice"},
        format="multipart",
    )
    assert res.status_code == 201
    body = res.json()
    doc = body["documents"][0]
    assert body["meta"] == {"source": "n8n", "sender": "a@b.pk", "subject": "Invoice"}
    detail = key.get(doc["status_url"]).json()
    assert detail["id"] == doc["id"] and detail["webhook_payload"]["extraction"]["total"] == 3500
    # documents landed in the key's workspace
    from apps.documents.models import Document

    assert Document.objects.get(pk=doc["id"]).workspace_id == world["ws"].id


def test_inbound_requires_an_api_key_and_never_crosses_workspaces(world, pipeline):
    url = "/api/v1/integrations/inbound/"
    assert client_for(world["users"]["owner"]).post(
        url, {"files": png()}, format="multipart"
    ).status_code in (401, 403)
    assert client_for().post(url, {"files": png()}, format="multipart").status_code == 401
    assert client_for(api_key=world["raw_key"]).post(url, {}, format="multipart").status_code == 400
    key = client_for(api_key=world["raw_key"])
    doc_id = key.post(url, {"files": png()}, format="multipart").json()["documents"][0]["id"]
    from apps.workspaces.models import ApiKey

    other_key, raw = ApiKey.issue(world["other"], "other")
    assert (
        client_for(api_key=raw).get(f"/api/v1/integrations/documents/{doc_id}/").status_code == 404
    )


def test_inbound_respects_workspace_upload_limits(world, pipeline):
    ws = world["ws"]
    ws.daily_upload_limit = 1
    ws.save()
    res = client_for(api_key=world["raw_key"]).post(
        "/api/v1/integrations/inbound/", {"files": [png("a.png"), png("b.png")]}, format="multipart"
    )
    assert res.status_code == 201 and len(res.json()["documents"]) == 1
    assert "limit" in res.json()["errors"][0]["error"].lower()
