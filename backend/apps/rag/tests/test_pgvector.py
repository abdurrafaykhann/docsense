"""Runs only on PostgreSQL + pgvector (CI service container / docker-compose).

    DATABASE_URL=postgres://docsense:docsense@localhost:5432/docsense \
        pytest apps/rag/tests/test_pgvector.py
"""

import pytest
from django.db import connection

from apps.rag import pgvector, search, service
from apps.rag.embedding import HashEmbedder
from apps.rag.models import Chunk
from apps.rag.rerank import OverlapReranker
from apps.rag.tests.test_rag import POLICY, make_doc

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL + pgvector"),
]
EMB384 = HashEmbedder(dim=384)


def vec_rows(where=""):
    with connection.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM rag_chunk_vec {where}")
        return cur.fetchone()[0]


def test_schema_has_vector_column_and_hnsw_index():
    with connection.cursor() as cur:
        cur.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'rag_chunk_vec_hnsw'")
        indexdef = cur.fetchone()[0]
        cur.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'rag_chunk_vec'::regclass AND attname = 'embedding'"
        )
        dim = cur.fetchone()[0]
    assert "hnsw" in indexdef and "vector_cosine_ops" in indexdef
    assert dim == pgvector.DIM


def test_indexing_mirrors_384d_embeddings_and_cascades_on_delete(world):
    d = make_doc(world["ws"], "policy.pdf", POLICY, embedder=EMB384)
    n = Chunk.objects.filter(document=d).count()
    assert n > 0 and vec_rows() == n
    Chunk.objects.filter(document=d).delete()  # FK ON DELETE CASCADE
    assert vec_rows() == 0


def test_non_384d_embeddings_are_not_mirrored_and_use_numpy(world):
    make_doc(world["ws"], "policy.pdf", POLICY)  # fixture default: 256-d hash embedder
    assert vec_rows() == 0


def test_retrieval_uses_the_ann_index_and_matches_numpy_ranking(world, monkeypatch):
    ws = world["ws"]
    make_doc(ws, "policy.pdf", POLICY, embedder=EMB384)
    make_doc(
        ws,
        "fuel.png",
        ["Petrol pump receipt", "Fuel purchase 40 litres of petrol", "Total fuel cost 12000"],
        embedder=EMB384,
    )
    q = "What is the warranty period for LED panels?"
    ann = pgvector.dense_candidates(ws.id, EMB384.name, EMB384.embed([q])[0], 5)
    assert ann and max(ann.values()) <= 1.0001
    top_ann = max(ann, key=ann.get)
    assert Chunk.objects.get(pk=top_ann).document.original_name == "policy.pdf"

    def boom(*a, **k):
        raise AssertionError("NumPy dense scan must not run when pgvector answered")

    monkeypatch.setattr(search, "dense_scores", boom)
    hits = service.retrieve(ws.id, q, embedder=EMB384, reranker=OverlapReranker())
    assert hits and hits[0]["chunk"].document.original_name == "policy.pdf"


def test_document_filter_and_workspace_scope_in_ann_query(world):
    a = make_doc(world["ws"], "policy.pdf", POLICY, embedder=EMB384)
    make_doc(world["other"], "secret.pdf", ["warranty period secret merger"], embedder=EMB384)
    q = EMB384.embed(["warranty period"])[0]
    in_ws = pgvector.dense_candidates(world["ws"].id, EMB384.name, q, 10)
    assert {Chunk.objects.get(pk=i).workspace_id for i in in_ws} == {world["ws"].id}
    only = pgvector.dense_candidates(world["ws"].id, EMB384.name, q, 10, document_ids=[a.id + 999])
    assert only == {}
