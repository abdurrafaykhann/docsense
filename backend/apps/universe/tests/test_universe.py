import numpy as np
import pytest

from apps.rag.embedding import HashEmbedder
from apps.rag.tests.test_rag import make_doc
from apps.universe import projection, service
from apps.universe.models import UniversePoint
from conftest import client_for

TOPICS = {
    "fuel": "petrol diesel litres pump fuel station nozzle tank",
    "grocery": "rice sugar milk flour tea eggs biscuits oil",
    "electronics": "led bulb charger cable fan socket earphones adapter",
}
EMB = HashEmbedder()


def corpus(per_topic=8):
    rng = np.random.default_rng(0)
    texts, topic = [], []
    for name, words in TOPICS.items():
        vocab = words.split()
        for _ in range(per_topic):
            texts.append("Invoice " + " ".join(rng.choice(vocab, size=6)) + " total")
            topic.append(name)
    return texts, topic


def test_normalize_cloud_centres_and_fits_unit_ball():
    xyz = normalized = projection.normalize_cloud(np.array([[10.0, 0, 0], [12, 0, 0], [11, 4, 0]]))
    assert np.allclose(xyz.mean(axis=0), 0, atol=1e-9) and np.linalg.norm(
        normalized, axis=1
    ).max() == pytest.approx(1)
    assert projection.normalize_cloud(np.zeros((0, 3))).shape == (0, 3)


def test_projection_shape_determinism_and_tiny_corpora():
    texts, _ = corpus()
    emb = EMB.embed(texts)
    a = projection.project_3d(emb, seed=1)
    b = projection.project_3d(emb, seed=1)
    assert a.shape == (24, 3) and np.linalg.norm(a, axis=1).max() <= 1 + 1e-6
    assert np.allclose(a, b)
    for n in (0, 1, 2, 4):  # below the UMAP minimum: PCA fallback must not crash
        out = projection.project_3d(emb[:n], seed=0)
        assert out.shape == (n, 3) and np.isfinite(out).all()


def test_similar_documents_land_together_and_clusters_are_labelled_by_topic():
    texts, topic = corpus()
    xyz = projection.project_3d(EMB.embed(texts), seed=0)
    labels = projection.cluster(xyz)
    clusters = [c for c in set(labels) if c >= 0]
    assert len(clusters) >= 2
    for c in clusters:  # every cluster is dominated by a single topic
        members = [topic[i] for i in range(len(topic)) if labels[i] == c]
        top = max(set(members), key=members.count)
        assert members.count(top) / len(members) >= 0.85
    names = projection.label_clusters(texts, labels)
    assert set(names) == set(clusters)
    for c, label in names.items():
        members = [topic[i] for i in range(len(topic)) if labels[i] == c]
        top = max(set(members), key=members.count)
        assert any(w in label for w in TOPICS[top].split()), (label, top)
    # intra-topic distances are smaller than inter-topic distances
    idx = {t: [i for i, x in enumerate(topic) if x == t] for t in TOPICS}
    intra = np.mean(
        [np.linalg.norm(xyz[i] - xyz[j]) for t in idx for i in idx[t] for j in idx[t] if i < j]
    )
    inter = np.mean([np.linalg.norm(xyz[i] - xyz[j]) for i in idx["fuel"] for j in idx["grocery"]])
    assert intra < inter


def test_label_clusters_without_clusters_or_vocabulary():
    assert projection.label_clusters(["a b"], np.array([-1])) == {}
    assert projection.label_clusters(["12 34", "56 78"], np.array([0, 1])) == {
        0: "cluster 1",
        1: "cluster 2",
    }


# -------------------------------------------------------------------------- service + API
pytestmark = pytest.mark.django_db


def seed_docs(ws, n_per=4):
    docs = []
    for topic, words in TOPICS.items():
        for i in range(n_per):
            docs.append(
                make_doc(ws, f"{topic}-{i}.png", [f"Receipt {topic} {i}", *words.split()[:6]])
            )
    return docs


def test_rebuild_places_every_indexed_document_and_replaces_old_points(world):
    seed_docs(world["ws"])
    out = service.rebuild(world["ws"].id)
    assert out["points"] == 12
    pts = UniversePoint.objects.filter(workspace=world["ws"])
    assert pts.count() == 12 and all(np.linalg.norm([p.x, p.y, p.z]) <= 1 + 1e-6 for p in pts)
    service.rebuild(world["ws"].id)
    assert UniversePoint.objects.filter(workspace=world["ws"]).count() == 12
    assert service.rebuild(world["other"].id) == {"points": 0, "clusters": 0}


def test_points_api_returns_metadata_clusters_and_respects_workspaces(world):
    seed_docs(world["ws"])
    make_doc(world["other"], "secret.png", ["Confidential merger codename Falcon"])
    service.rebuild(world["ws"].id)
    service.rebuild(world["other"].id)
    c = client_for(world["users"]["viewer"])
    data = c.get(f"/api/v1/workspaces/{world['ws'].id}/universe/points/").json()
    assert len(data["points"]) == 12 and {"id", "name", "x", "y", "z", "cluster", "vendor"} <= set(
        data["points"][0]
    )
    assert all("secret" not in p["name"] for p in data["points"])
    for cl in data["clusters"]:
        assert len(cl["centroid"]) == 3 and cl["n"] >= 1
    out = (
        client_for(world["users"]["outsider"])
        .get(f"/api/v1/workspaces/{world['other'].id}/universe/points/")
        .json()
    )
    assert [p["name"] for p in out["points"]] == ["secret.png"]
    assert (
        client_for(world["users"]["outsider"])
        .get(f"/api/v1/workspaces/{world['ws'].id}/universe/points/")
        .status_code
        == 404
    )
    assert (
        client_for().get(f"/api/v1/workspaces/{world['ws'].id}/universe/points/").status_code == 401
    )


def test_rebuild_endpoint_needs_member_role(world):
    seed_docs(world["ws"])
    url = f"/api/v1/workspaces/{world['ws'].id}/universe/rebuild/"
    assert client_for(world["users"]["viewer"]).post(url).status_code == 403
    res = client_for(world["users"]["member"]).post(url)
    assert res.status_code == 200 and res.json()["points"] == 12
