"""Hybrid retrieval: dense cosine + BM25 keyword search, fused with Reciprocal Rank Fusion."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .embedding import content_tokens, from_blob

RRF_K = 60


@dataclass
class Candidate:
    chunk_id: int
    dense: float = 0.0  # cosine similarity
    bm25: float = 0.0
    rrf: float = 0.0
    rerank: float = 0.0


def dense_scores(query_vec: np.ndarray, blobs: list[bytes]) -> np.ndarray:
    if not blobs:
        return np.zeros(0, dtype=np.float32)
    return np.stack([from_blob(b) for b in blobs]) @ query_vec.astype(np.float32)


def bm25_scores(query: str, texts: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    """Okapi BM25 over the candidate corpus (documents = chunks)."""
    q = content_tokens(query)
    docs = [content_tokens(t) for t in texts]
    n = len(docs)
    if not n or not q:
        return np.zeros(n, dtype=np.float32)
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df = Counter(t for d in docs for t in set(d))
    out = np.zeros(n, dtype=np.float32)
    for i, d in enumerate(docs):
        tf = Counter(d)
        for t in set(q):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            out[i] += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
    return out


def rrf(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion: score(d) = sum 1 / (k + rank)."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
    return fused


def hybrid_search(
    query: str,
    query_vec: np.ndarray,
    chunk_ids: list[int],
    texts: list[str],
    blobs: list[bytes],
    top_k: int = 20,
    dense_override: dict[int, float] | None = None,
) -> list[Candidate]:
    """`dense_override` ({chunk_id: cosine}) replaces the NumPy scan when pgvector did the ANN."""
    if not chunk_ids:
        return []
    if dense_override is not None:
        dense = np.array([dense_override.get(cid, 0.0) for cid in chunk_ids], dtype=np.float32)
    else:
        dense = dense_scores(query_vec, blobs)
    kw = bm25_scores(query, texts)
    dense_rank = [
        chunk_ids[i]
        for i in np.argsort(-dense)[:top_k]
        if dense_override is None or dense[i] != 0.0 or chunk_ids[i] in dense_override
    ]
    # keyword ranking only includes chunks that matched at least one query term
    kw_rank = [chunk_ids[i] for i in np.argsort(-kw)[:top_k] if kw[i] > 0]
    fused = rrf([dense_rank, kw_rank])
    by_id = {cid: i for i, cid in enumerate(chunk_ids)}
    cands = [
        Candidate(cid, float(dense[by_id[cid]]), float(kw[by_id[cid]]), score)
        for cid, score in fused.items()
    ]
    return sorted(cands, key=lambda c: -c.rrf)[:top_k]
