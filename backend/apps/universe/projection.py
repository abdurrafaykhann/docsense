"""Embeddings -> 3D positions (UMAP) -> clusters (HDBSCAN) -> readable labels (TF-IDF).

Pure NumPy/scikit-learn/UMAP: no Django, deterministic for a fixed seed.
"""

from __future__ import annotations

import numpy as np

MIN_FOR_UMAP = 6


def normalize_cloud(xyz: np.ndarray) -> np.ndarray:
    """Centre and scale into a unit-radius ball so the camera always frames the cloud."""
    if len(xyz) == 0:
        return xyz
    xyz = xyz - xyz.mean(axis=0)
    radius = np.linalg.norm(xyz, axis=1).max()
    return xyz / radius if radius > 0 else xyz


def project_3d(embeddings: np.ndarray, seed: int = 0) -> np.ndarray:
    """UMAP (cosine) to 3 dimensions. Tiny corpora fall back to PCA (UMAP needs >= ~6 points)."""
    n = len(embeddings)
    if n == 0:
        return np.zeros((0, 3))
    if n < MIN_FOR_UMAP:
        centered = embeddings - embeddings.mean(axis=0)
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        comps = vt[:3]
        out = centered @ comps.T
        if out.shape[1] < 3:
            out = np.pad(out, ((0, 0), (0, 3 - out.shape[1])))
        return normalize_cloud(out)
    import umap

    reducer = umap.UMAP(
        n_components=3,
        n_neighbors=min(15, n - 1),
        min_dist=0.15,
        metric="cosine",
        random_state=seed,
        init="random" if n < 12 else "spectral",
    )
    return normalize_cloud(reducer.fit_transform(embeddings))


def cluster(xyz: np.ndarray, min_cluster_size: int | None = None) -> np.ndarray:
    """HDBSCAN on the 3D coordinates; -1 = noise (unclustered)."""
    n = len(xyz)
    if n < 4:
        return np.zeros(n, dtype=int)
    from sklearn.cluster import HDBSCAN

    size = min_cluster_size or max(2, n // 12)
    return HDBSCAN(min_cluster_size=size, min_samples=1).fit_predict(xyz)


def label_clusters(texts: list[str], labels: np.ndarray, top: int = 3) -> dict[int, str]:
    """Top TF-IDF terms of each cluster's concatenated text (distinct from the other clusters)."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    ids = sorted(set(int(c) for c in labels if c >= 0))
    if not ids:
        return {}
    docs = [" ".join(t for t, c in zip(texts, labels, strict=True) if c == i) for i in ids]
    vec = TfidfVectorizer(stop_words="english", token_pattern=r"[A-Za-z][A-Za-z\-]{2,}", max_df=0.9)
    try:
        matrix = vec.fit_transform(docs)
    except ValueError:  # empty vocabulary
        return {i: f"cluster {i + 1}" for i in ids}
    terms = np.array(vec.get_feature_names_out())
    out = {}
    for row, cid in enumerate(ids):
        weights = matrix[row].toarray().ravel()
        best = terms[np.argsort(-weights)[:top]]
        out[cid] = ", ".join(
            t for t, w in zip(best, np.sort(weights)[::-1][:top], strict=False) if w > 0
        )
        out[cid] = out[cid] or f"cluster {cid + 1}"
    return out
