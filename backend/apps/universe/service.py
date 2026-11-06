"""Build the document universe for a workspace."""

from __future__ import annotations

import numpy as np
from django.db import transaction

from apps.documents.models import Document
from apps.rag.embedding import from_blob
from apps.rag.models import Chunk
from apps.rag.service import get_embedder

from . import projection
from .models import UniversePoint


def document_vectors(
    workspace_id: int, embedder_name: str
) -> tuple[list[Document], np.ndarray, list[str]]:
    """One vector per document: the normalised mean of its chunk embeddings."""
    by_doc: dict[int, list[np.ndarray]] = {}
    texts: dict[int, list[str]] = {}
    for c in Chunk.objects.filter(workspace_id=workspace_id, embedder=embedder_name):
        by_doc.setdefault(c.document_id, []).append(from_blob(c.embedding))
        texts.setdefault(c.document_id, []).append(c.text)
    docs = list(
        Document.objects.filter(workspace_id=workspace_id, id__in=by_doc).select_related(
            "invoice__vendor"
        )
    )
    vecs, doc_texts = [], []
    for d in docs:
        m = np.mean(by_doc[d.id], axis=0)
        n = np.linalg.norm(m)
        vecs.append(m / n if n else m)
        doc_texts.append(" ".join(texts[d.id]))
    return docs, (np.stack(vecs) if vecs else np.zeros((0, 1))), doc_texts


@transaction.atomic
def rebuild(workspace_id: int, seed: int = 0) -> dict:
    embedder = get_embedder()
    docs, vectors, texts = document_vectors(workspace_id, embedder.name)
    UniversePoint.objects.filter(workspace_id=workspace_id).delete()
    if not docs:
        return {"points": 0, "clusters": 0}
    xyz = projection.project_3d(vectors, seed=seed)
    labels = projection.cluster(xyz)
    names = projection.label_clusters(texts, labels)
    UniversePoint.objects.bulk_create(
        UniversePoint(
            document=d,
            workspace_id=workspace_id,
            x=float(p[0]),
            y=float(p[1]),
            z=float(p[2]),
            cluster=int(c),
            cluster_label=names.get(int(c), ""),
        )
        for d, p, c in zip(docs, xyz, labels, strict=True)
    )
    return {"points": len(docs), "clusters": len(names)}
