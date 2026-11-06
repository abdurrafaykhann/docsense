"""Optional pgvector acceleration for the dense half of hybrid search.

On PostgreSQL (docker-compose, CI, production) chunk embeddings are mirrored into a
`rag_chunk_vec` table with a `vector(384)` column and an HNSW cosine index, and the dense
candidate list comes from the database (`<=>` operator). On SQLite (local dev, unit tests) this
module is inert and the brute-force NumPy cosine in search.py is used. Only 384-d embeddings
(MiniLM) are mirrored; other dimensions fall back to NumPy.
"""

from __future__ import annotations

import numpy as np
from django.db import connection

DIM = 384

CREATE_SQL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"""CREATE TABLE IF NOT EXISTS rag_chunk_vec (
        chunk_id bigint PRIMARY KEY REFERENCES rag_chunk(id) ON DELETE CASCADE,
        workspace_id bigint NOT NULL,
        embedder varchar(60) NOT NULL,
        embedding vector({DIM}) NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS rag_chunk_vec_ws ON rag_chunk_vec (workspace_id, embedder)",
    "CREATE INDEX IF NOT EXISTS rag_chunk_vec_hnsw ON rag_chunk_vec "
    "USING hnsw (embedding vector_cosine_ops)",
]


def available() -> bool:
    return connection.vendor == "postgresql"


def literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


def create_schema(schema_editor=None) -> None:
    conn = schema_editor.connection if schema_editor else connection
    with conn.cursor() as cur:
        for sql in CREATE_SQL:
            cur.execute(sql)


def mirror(chunks, vectors: np.ndarray) -> int:
    """Insert/refresh vector rows for new Chunk objects (needs 384-d vectors)."""
    if not available() or vectors.shape[1] != DIM or not chunks:
        return 0
    rows = [
        (c.id, c.workspace_id, c.embedder, literal(v)) for c, v in zip(chunks, vectors, strict=True)
    ]
    with connection.cursor() as cur:
        cur.executemany(
            "INSERT INTO rag_chunk_vec (chunk_id, workspace_id, embedder, embedding) "
            "VALUES (%s, %s, %s, %s::vector) "
            "ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding",
            rows,
        )
    return len(rows)


def dense_candidates(
    workspace_id: int,
    embedder: str,
    query_vec: np.ndarray,
    top_k: int = 20,
    document_ids: list[int] | None = None,
) -> dict[int, float]:
    """{chunk_id: cosine similarity} for the top_k nearest chunks (HNSW index scan)."""
    if not available() or len(query_vec) != DIM:
        return {}
    sql = (
        "SELECT v.chunk_id, 1 - (v.embedding <=> %s::vector) "
        "FROM rag_chunk_vec v JOIN rag_chunk c ON c.id = v.chunk_id "
        "WHERE v.workspace_id = %s AND v.embedder = %s"
    )
    params: list = [literal(query_vec), workspace_id, embedder]
    if document_ids:
        sql += " AND c.document_id = ANY(%s)"
        params.append(document_ids)
    sql += " ORDER BY v.embedding <=> %s::vector LIMIT %s"
    params += [literal(query_vec), top_k]
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return {int(cid): float(sim) for cid, sim in cur.fetchall()}
