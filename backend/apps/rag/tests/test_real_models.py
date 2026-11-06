"""Real local models (downloads ~180 MB on first run): pytest -m slow --force-enable-socket"""

import numpy as np
import pytest

pytestmark = [pytest.mark.slow, pytest.mark.enable_socket]


def test_minilm_embeddings_are_semantic_and_cross_encoder_ranks_relevance():
    pytest.importorskip("sentence_transformers")
    from apps.rag.embedding import SentenceTransformerEmbedder
    from apps.rag.rerank import CrossEncoderReranker

    emb = SentenceTransformerEmbedder()
    v = emb.embed(
        [
            "How long is the warranty?",
            "The warranty period is 24 months from purchase.",
            "Fuel purchase of 40 litres of petrol.",
        ]
    )
    assert v.shape == (3, 384) and np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-3)
    assert v[0] @ v[1] > v[0] @ v[2] + 0.2

    rr = CrossEncoderReranker()
    good, bad = rr.score(
        "How long is the warranty?",
        [
            "The warranty period is 24 months from purchase.",
            "Fuel purchase of 40 litres of petrol.",
        ],
    )
    assert good > 0.5 > rr.min_score + 0.4 > bad
