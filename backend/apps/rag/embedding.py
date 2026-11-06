"""Embedders: local sentence-transformers in production, deterministic hashing in tests."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an the of to in on for and or is are was were be been what which who whom how much many "
    "did do does we our you your i me my it its this that these those with from by at as per "
    "show tell give list find me about all any".split()
)


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS]


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    """Signed feature hashing of unigrams + bigrams (sublinear tf). No downloads, deterministic.

    Good enough to make 'similar words -> similar vectors' tests meaningful; not for production.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"hash-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = content_tokens(text)
        grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        counts: dict[str, int] = {}
        for g in grams:
            counts[g] = counts.get(g, 0) + 1
        for g, c in counts.items():
            h = int.from_bytes(hashlib.md5(g.encode()).digest()[:8], "little")
            v[h % self.dim] += (1.0 if (h >> 63) & 1 else -1.0) * (1 + np.log(c))
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return (
            np.stack([self._vec(t) for t in texts])
            if texts
            else np.zeros((0, self.dim), np.float32)
        )


class SentenceTransformerEmbedder:
    """all-MiniLM-L6-v2 (384-d), CPU, free. Lazy-loaded once per process."""

    _model = None

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.name = model_name.split("/")[-1]

    def embed(self, texts: list[str]) -> np.ndarray:
        if SentenceTransformerEmbedder._model is None:
            from sentence_transformers import SentenceTransformer

            SentenceTransformerEmbedder._model = SentenceTransformer(self.model_name, device="cpu")
        out = SentenceTransformerEmbedder._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return out.astype(np.float32)


def to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(bytes(b), dtype=np.float32)
