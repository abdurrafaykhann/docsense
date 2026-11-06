import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.analytics.models import Flag
from apps.documents.models import Document, Invoice
from apps.rag import service as rag
from apps.rag.embedding import HashEmbedder
from apps.rag.rerank import OverlapReranker
from apps.workspaces.models import Workspace
from conftest import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def django_db_setup(django_db_setup):  # noqa: F811 - reuse pytest-django's test database
    return django_db_setup


@pytest.fixture
def seeded(db):
    call_command("seed_demo", "--no-universe")
    return Workspace.objects.get(slug="demo-traders")


def test_seed_creates_about_fifty_documents_with_review_queue_and_demo_login(seeded, client):
    assert seeded.is_demo and Document.objects.filter(workspace=seeded).count() == 50
    assert Invoice.objects.filter(workspace=seeded).count() == 47  # 3 await human review
    assert Document.objects.filter(workspace=seeded, status="needs_review").count() == 3
    res = client.post(
        "/api/v1/auth/login/",
        {"email": "demo@docsense.dev", "password": "docsense-demo-2025"},
        content_type="application/json",
    )
    assert res.status_code == 200
    token = res.json()["access"]
    me = client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {token}").json()
    assert me["workspaces"][0]["slug"] == "demo-traders" and me["user"]["is_staff"] is True


def test_seed_is_idempotent_and_reset_rebuilds(seeded):
    call_command("seed_demo", "--no-universe")
    assert Document.objects.filter(workspace=seeded).count() == 50
    call_command("seed_demo", "--no-universe", "--reset")
    new = Workspace.objects.get(slug="demo-traders")
    assert Document.objects.filter(workspace=new).count() == 50 and new.id != seeded.id


def test_planted_anomalies_are_detected_and_real_templates_are_not_over_flagged(seeded):
    flags = list(Flag.objects.filter(workspace=seeded).select_related("document"))
    kinds = {f.kind for f in flags}
    assert {"price_creep", "amount_outlier", "exact_dup", "near_dup"} <= kinds
    dup = next(f for f in flags if f.kind == "exact_dup")
    assert dup.document.original_name.endswith("(copy).jpg")
    creep = next(f for f in flags if f.kind == "price_creep")
    assert creep.evidence["increase_pct"] >= 30
    # regression: same-template invoices from one vendor must not all be 'image duplicates'
    assert sum(f.kind == "image_dup" for f in flags) <= 3
    assert len(flags) <= 14


def test_seeded_documents_are_viewable_searchable_and_reviewable(seeded, client):
    doc = Document.objects.filter(workspace=seeded, status="needs_review").first()
    owner = client_for(seeded.memberships.get().user)
    base = f"/api/v1/workspaces/{seeded.id}"
    detail = owner.get(f"{base}/documents/{doc.id}/").json()
    assert detail["pages"][0]["regions"] and any(
        i["code"] == "total_mismatch" for i in detail["extraction"]["issues"]
    )
    total = next(f for f in detail["extraction"]["fields"] if f["name"] == "total")
    assert total["bbox"] is not None  # field boxes come from the pack, so the viewer can highlight
    assert owner.get(f"{base}/documents/{doc.id}/pages/1/image/").status_code == 200
    assert owner.get(f"{base}/review/queue/").json()["count"] == 3
    # retrieval works over the seeded chunks (hash embedder under test settings)
    hits = rag.retrieve(
        seeded.id,
        "Hashmi Services invoice total",
        embedder=HashEmbedder(),
        reranker=OverlapReranker(),
    )
    assert hits and "Hashmi" in hits[0]["chunk"].document.original_name or hits[0]["rerank"] > 0
    summary = owner.get(f"{base}/analytics/summary/").json()
    assert summary["invoices"] == 47 and summary["vendors"] == 7 and summary["total_spend"] > 0


def test_missing_pack_is_a_clear_error(settings, tmp_path):
    settings.SEED_DIR = tmp_path
    with pytest.raises(CommandError, match="Demo pack not found"):
        call_command("seed_demo")
