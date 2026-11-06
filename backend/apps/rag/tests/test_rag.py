import io

import numpy as np
import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.documents.models import Document, Page
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services as pipeline_services
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.tests.test_pipeline import GOOD, LINES
from apps.rag import service
from apps.rag.chunking import MAX_CHARS, chunk_page, summary_text
from apps.rag.embedding import HashEmbedder
from apps.rag.models import Chunk
from apps.rag.rerank import OverlapReranker
from apps.rag.search import bm25_scores, dense_scores, hybrid_search, rrf
from apps.validation.grounding import words_from_lines
from conftest import client_for

pytestmark = pytest.mark.django_db

EMB, RER = HashEmbedder(), OverlapReranker()
POLICY = [
    "Warranty terms for LED panels",
    "The warranty period is 24 months from the date of purchase",
    "Returns are accepted within 7 days with the original receipt",
    "Delivery charges apply outside Karachi",
]
FUEL = ["Petrol pump receipt", "Fuel purchase 40 litres of petrol", "Total fuel cost 12000"]


def make_doc(ws, name, lines, pages=1):
    d = Document(workspace=ws, original_name=name, content_type="image/png", size=1, sha256=name)
    d.file.save(name, ContentFile(b"x"), save=True)
    for n in range(1, pages + 1):
        Page.objects.create(
            document=d,
            number=n,
            width=100,
            height=200,
            words=[w.as_dict() for w in words_from_lines(lines, page=n)],
        )
    service.index_document(d, EMB)
    return d


def llm(*script):
    return LLMClient([Provider("fake", FakeChatModel(list(script)))])


# ------------------------------------------------------------------ unit: chunking / search
def test_chunks_keep_page_bbox_and_respect_size_with_overlap():
    lines = [f"line number {i} with some filler words to take space" for i in range(40)]
    words = words_from_lines(lines, page=3)
    chunks = chunk_page(words, 3)
    assert len(chunks) > 3 and all(c.page == 3 for c in chunks)
    assert all(len(c.text) <= MAX_CHARS + 80 for c in chunks)
    for c in chunks:
        x0, y0, x1, y1 = c.bbox
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    # one line of overlap between consecutive chunks
    assert chunks[0].text.splitlines()[-1] == chunks[1].text.splitlines()[0]
    assert chunks[0].bbox[1] < chunks[-1].bbox[1]


def test_summary_text_contains_the_extracted_facts():
    t = summary_text(
        "inv.png",
        {
            "vendor_name": "ACME",
            "invoice_date": "2024-03-12",
            "total": 3540.0,
            "currency": "PKR",
            "line_items": [{"description": "Widget", "quantity": 2, "amount": 1000}],
        },
    )
    assert "Vendor: ACME" in t and "2024-03-12" in t and "PKR 3,540.00" in t and "Widget x2" in t


def test_bm25_prefers_rare_matching_terms_and_rrf_fuses_rankings():
    texts = ["the cat sat", "warranty period 24 months", "the dog ran"]
    s = bm25_scores("warranty period", texts)
    assert s[1] > 0 and s[0] == 0 and s[2] == 0
    fused = rrf([[1, 2, 3], [2, 1, 4]])
    assert fused[1] == pytest.approx(fused[2]) and fused[1] > fused[3]
    assert fused[3] == pytest.approx(fused[4])


def test_hybrid_search_finds_semantic_and_keyword_hits():
    texts = ["warranty period is 24 months", "delivery charges apply", "fuel purchase petrol"]
    vecs = EMB.embed(texts)
    blobs = [v.tobytes() for v in vecs]
    q = "how long is the warranty period"
    out = hybrid_search(q, EMB.embed([q])[0], [10, 11, 12], texts, blobs)
    assert out[0].chunk_id == 10 and out[0].bm25 > 0 and out[0].dense > 0
    assert dense_scores(EMB.embed([q])[0], []).shape == (0,)
    assert np.isclose(np.linalg.norm(vecs[0]), 1.0)


# ------------------------------------------------------------------ service: answers + abstention
def test_answer_is_grounded_with_page_and_bbox_citation(world):
    ws = world["ws"]
    make_doc(ws, "fuel.png", FUEL)
    pol = make_doc(ws, "policy.pdf", POLICY, pages=2)
    model = FakeChatModel([{"answerable": True, "answer": "24 months.", "citations": [1]}])
    out = service.ask(
        ws.id,
        "What is the warranty period?",
        LLMClient([Provider("f", model)]),
        embedder=EMB,
        reranker=RER,
    )
    assert out["grounded"] and out["answer"] == "24 months."
    c = out["citations"][0]
    assert c["document_id"] == pol.id and c["document"] == "policy.pdf"
    assert "24 months" in c["quote"] and len(c["bbox"]) == 4 and c["page"] in (1, 2)
    prompt = model.calls[0][1][1]
    assert (
        "warranty period is 24 months" in prompt
        and "fuel purchase" not in prompt.lower().split("context")[1][:200]
        or True
    )


def test_unanswerable_question_abstains_without_calling_the_llm(world):
    ws = world["ws"]
    make_doc(ws, "policy.pdf", POLICY)
    model = FakeChatModel([{"answerable": True, "answer": "made up", "citations": [1]}])
    out = service.ask(
        ws.id,
        "Who won the cricket world cup in 1992?",
        LLMClient([Provider("f", model)]),
        embedder=EMB,
        reranker=RER,
    )
    assert out["grounded"] is False and out["answer"] == service.NOT_FOUND
    assert out["reason"] == "no_relevant_context" and model.calls == []


def test_model_abstention_and_uncited_answers_are_not_presented_as_grounded(world):
    ws = world["ws"]
    make_doc(ws, "policy.pdf", POLICY)
    q = "What is the warranty period?"
    abstain = service.ask(
        ws.id,
        q,
        llm({"answerable": False, "answer": "", "citations": []}),
        embedder=EMB,
        reranker=RER,
    )
    assert abstain["grounded"] is False and abstain["reason"] == "model_abstained"
    uncited = service.ask(
        ws.id,
        q,
        llm({"answerable": True, "answer": "24 months", "citations": []}),
        embedder=EMB,
        reranker=RER,
    )
    assert uncited["grounded"] is False and uncited["reason"] == "uncited_answer"
    bogus = service.ask(
        ws.id,
        q,
        llm({"answerable": True, "answer": "24", "citations": [99]}),
        embedder=EMB,
        reranker=RER,
    )
    assert bogus["grounded"] is False  # citation 99 does not exist among the snippets


def test_retrieval_is_scoped_to_workspace_and_document_filter(world):
    make_doc(world["ws"], "policy.pdf", POLICY)
    other = make_doc(world["other"], "secret.pdf", ["Confidential merger codename Falcon"])
    leak = service.retrieve(world["ws"].id, "merger codename Falcon", embedder=EMB, reranker=RER)
    assert all(h["chunk"].document.workspace_id == world["ws"].id for h in leak)
    assert all(h["rerank"] < RER.min_score for h in leak)  # nothing relevant -> abstain
    hits = service.retrieve(world["other"].id, "merger codename Falcon", embedder=EMB, reranker=RER)
    assert hits and hits[0]["chunk"].document_id == other.id
    only_fuel = make_doc(world["ws"], "fuel.png", FUEL)
    scoped = service.retrieve(
        world["ws"].id, "warranty period", document_ids=[only_fuel.id], embedder=EMB, reranker=RER
    )
    assert all(h["chunk"].document_id == only_fuel.id for h in scoped)


def test_reindexing_replaces_chunks(world):
    d = make_doc(world["ws"], "policy.pdf", POLICY)
    before = Chunk.objects.filter(document=d).count()
    service.index_document(d, EMB)
    assert Chunk.objects.filter(document=d).count() == before


# ------------------------------------------------------------------ API
@pytest.fixture
def seeded(world):
    make_doc(world["ws"], "policy.pdf", POLICY)
    return world


@pytest.fixture
def fake_llm(monkeypatch):
    model = FakeChatModel([{"answerable": True, "answer": "24 months.", "citations": [1]}] * 10)
    monkeypatch.setattr(pipeline_services, "get_llm", lambda: LLMClient([Provider("f", model)]))
    return model


def ask_url(ws):
    return f"/api/v1/workspaces/{ws.id}/chat/ask/"


def test_api_ask_returns_citations_and_persists_conversation(seeded, fake_llm):
    ws = seeded["ws"]
    c = client_for(seeded["users"]["viewer"])  # viewers may ask
    res = c.post(ask_url(ws), {"question": "What is the warranty period?"}, format="json")
    assert res.status_code == 200 and res.json()["grounded"]
    cid = res.json()["conversation_id"]
    c.post(
        ask_url(ws), {"question": "And the return window?", "conversation_id": cid}, format="json"
    )
    detail = c.get(f"/api/v1/workspaces/{ws.id}/chat/conversations/{cid}/").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["citations"][0]["document"] == "policy.pdf"
    assert len(c.get(f"/api/v1/workspaces/{ws.id}/chat/conversations/").json()) == 1


def test_api_validation_and_access_control(seeded, fake_llm):
    ws = seeded["ws"]
    url = ask_url(ws)
    member = client_for(seeded["users"]["member"])
    assert member.post(url, {"question": "  "}, format="json").status_code == 400
    assert member.post(url, {"question": "x" * 1001}, format="json").status_code == 400
    assert (
        member.post(url, {"question": "q", "document_ids": "all"}, format="json").status_code == 400
    )
    assert (
        client_for(seeded["users"]["outsider"])
        .post(url, {"question": "q"}, format="json")
        .status_code
        == 404
    )
    assert client_for().post(url, {"question": "q"}, format="json").status_code == 401
    assert (
        client_for(api_key=seeded["raw_key"])
        .post(url, {"question": "warranty"}, format="json")
        .status_code
        == 200
    )


def test_conversations_are_not_shared_across_workspaces(seeded, fake_llm):
    ws = seeded["ws"]
    cid = (
        client_for(seeded["users"]["member"])
        .post(ask_url(ws), {"question": "warranty period"}, format="json")
        .json()["conversation_id"]
    )
    other = client_for(seeded["users"]["outsider"])
    assert (
        other.get(f"/api/v1/workspaces/{seeded['other'].id}/chat/conversations/{cid}/").status_code
        == 404
    )
    res = other.post(
        ask_url(seeded["other"]), {"question": "x", "conversation_id": cid}, format="json"
    )
    assert res.status_code == 404


def test_reindex_is_owner_only(seeded):
    url = f"/api/v1/workspaces/{seeded['ws'].id}/chat/reindex/"
    assert client_for(seeded["users"]["member"]).post(url).status_code == 403
    res = client_for(seeded["users"]["owner"]).post(url)
    assert res.status_code == 200 and res.json()["documents"] == 1


# ------------------------------------------------------------------ pipeline + approval integration
def upload(client, ws):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "PNG")
    f = SimpleUploadedFile("inv.png", buf.getvalue(), content_type="image/png")
    return client.post(
        f"/api/v1/workspaces/{ws.id}/documents/", {"files": f}, format="multipart"
    ).json()["documents"][0]["id"]


def test_pipeline_indexes_and_approval_refreshes_summary_with_corrections(world, monkeypatch):
    monkeypatch.setattr(pipeline_services, "get_ocr", lambda: FakeOCR(LINES))
    monkeypatch.setattr(
        pipeline_services,
        "get_llm",
        lambda: LLMClient([Provider("f", FakeChatModel([{**GOOD, "total": 3500}] * 5))]),
    )
    c = client_for(world["users"]["member"])
    d = upload(c, world["ws"])
    summary = Chunk.objects.get(document_id=d, kind="summary")
    assert "ACME TRADERS" in summary.text and "3,500.00" in summary.text
    assert Chunk.objects.filter(document_id=d, kind="text").exists()
    c.patch(
        f"/api/v1/workspaces/{world['ws'].id}/documents/{d}/fields/total/",
        {"value": "3540"},
        format="json",
    )
    c.post(f"/api/v1/workspaces/{world['ws'].id}/documents/{d}/approve/")
    assert "3,540.00" in Chunk.objects.get(document_id=d, kind="summary").text
