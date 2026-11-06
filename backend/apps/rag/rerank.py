"""Re-ranking of the fused candidates. Scores are in [0, 1]; `min_score` is the abstain floor."""

from __future__ import annotations

import math
from typing import Protocol

from .embedding import content_tokens


class Reranker(Protocol):
    name: str
    min_score: float

    def score(self, query: str, texts: list[str]) -> list[float]: ...


class OverlapReranker:
    """Fraction of query content-words found in the passage (offline stand-in for tests)."""

    name = "overlap"
    min_score = 0.34

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = set(content_tokens(query))
        if not q:
            return [0.0] * len(texts)
        return [len(q & set(content_tokens(t))) / len(q) for t in texts]


class CrossEncoderReranker:
    """cross-encoder/ms-marco-MiniLM-L-6-v2: relevant passages score >0.5, noise < 0.05."""

    name = "ms-marco-MiniLM-L-6-v2"
    min_score = 0.05
    _model = None

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        if CrossEncoderReranker._model is None:
            from sentence_transformers import CrossEncoder

            CrossEncoderReranker._model = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu"
            )
        logits = CrossEncoderReranker._model.predict([(query, t) for t in texts])
        return [1 / (1 + math.exp(-float(x))) for x in logits]
