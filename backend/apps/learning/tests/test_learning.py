import io
import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image

from apps.documents.models import AuditEvent, Region
from apps.learning import services
from apps.learning.models import ModelVersion, RetrainJob, TrainingSample
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services as pipeline_services
from apps.pipeline.layout import FakeLayout
from apps.pipeline.layout import Region as LRegion
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.tests.test_pipeline import GOOD, LINES
from conftest import client_for

pytestmark = pytest.mark.django_db

REGIONS = [
    LRegion("vendor", [0.05, 0.02, 0.95, 0.2], 0.9),
    LRegion("table", [0.05, 0.3, 0.95, 0.6], 0.8),
    LRegion("totals", [0.5, 0.65, 0.95, 0.8], 0.7),
]


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    monkeypatch.setattr(pipeline_services, "get_ocr", lambda: FakeOCR(LINES))
    monkeypatch.setattr(
        pipeline_services,
        "get_llm",
        lambda: LLMClient([Provider("fake", FakeChatModel([{**GOOD, "total": 3500}] * 30))]),
    )
    monkeypatch.setattr(pipeline_services, "get_layout", lambda: FakeLayout(REGIONS))


def upload(client, ws):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, "PNG")
    f = SimpleUploadedFile("inv.png", buf.getvalue(), content_type="image/png")
    res = client.post(f"/api/v1/workspaces/{ws.id}/documents/", {"files": f}, format="multipart")
    return res.json()["documents"][0]["id"]


def u(ws, doc, suffix=""):
    return f"/api/v1/workspaces/{ws.id}/documents/{doc}/{suffix}"


@pytest.fixture
def doc(world):
    c = client_for(world["users"]["member"])
    return c, upload(c, world["ws"])


# ---------------------------------------------------------------- region editing
def test_member_can_replace_regions_and_it_is_audited(world, doc):
    c, d = doc
    new = [
        {"cls": "table", "bbox": [0.1, 0.35, 0.9, 0.55]},
        {"cls": "totals", "bbox": [0.9, 0.8, 0.5, 0.6]},  # reversed corners get ordered
    ]
    res = c.put(u(world["ws"], d, "pages/1/regions/"), {"regions": new}, format="json")
    assert res.status_code == 200
    assert [r["source"] for r in res.json()] == ["human", "human"]
    assert res.json()[1]["bbox"] == [0.5, 0.6, 0.9, 0.8]
    assert sorted(Region.objects.filter(page__document_id=d).values_list("cls", flat=True)) == [
        "table",
        "totals",
    ]
    ev = AuditEvent.objects.get(action="regions_edited")
    assert ev.detail == {"page": 1, "before": 3, "after": 2}


def test_region_edit_validation_and_permissions(world, doc):
    c, d = doc
    url = u(world["ws"], d, "pages/1/regions/")
    bad_class = c.put(url, {"regions": [{"cls": "logo", "bbox": [0, 0, 1, 1]}]}, format="json")
    assert bad_class.status_code == 400
    assert (
        c.put(url, {"regions": [{"cls": "table", "bbox": [0, 0]}]}, format="json").status_code
        == 400
    )
    assert c.put(url, {"regions": "nope"}, format="json").status_code == 400
    assert Region.objects.filter(page__document_id=d).count() == 3  # nothing changed
    viewer = client_for(world["users"]["viewer"])
    assert viewer.put(url, {"regions": []}, format="json").status_code == 403
    out = client_for(world["users"]["outsider"])
    assert out.put(url, {"regions": []}, format="json").status_code == 404


# ---------------------------------------------------------------- capture + export
def test_approval_creates_training_sample_with_final_regions_and_truth(world, doc):
    c, d = doc
    ws = world["ws"]
    c.put(
        u(ws, d, "pages/1/regions/"),
        {"regions": [{"cls": "table", "bbox": [0, 0.3, 1, 0.6]}]},
        format="json",
    )
    c.patch(u(ws, d, "fields/total/"), {"value": "3540"}, format="json")
    assert c.post(u(ws, d, "approve/")).status_code == 200
    s = TrainingSample.objects.get(document_id=d)
    assert s.corrected is True and s.regions == [{"cls": "table", "bbox": [0.0, 0.3, 1.0, 0.6]}]
    assert s.truth["total"] == 3540 and s.field_boxes["vendor_name"]
    assert s.image.size > 0


def test_uncorrected_approval_is_marked_not_corrected_and_is_idempotent(world, doc):
    c, d = doc
    ws = world["ws"]
    c.patch(u(ws, d, "fields/total/"), {"value": "3540"}, format="json")
    TrainingSample.objects.all().delete()
    AuditEvent.objects.all().delete()  # pretend nothing was edited
    c.post(u(ws, d, "approve/"))
    c.post(u(ws, d, "approve/"))
    assert TrainingSample.objects.count() == 1
    assert TrainingSample.objects.get().corrected is False


def test_export_writes_yolo_dataset_and_manifest(world, doc, tmp_path):
    c, d = doc
    c.post(u(world["ws"], d, "approve/"))
    n = services.export_feedback(tmp_path)
    assert n == 1
    label = next((tmp_path / "labels" / "train").glob("*.txt")).read_text().splitlines()
    assert sorted(int(line.split()[0]) for line in label) == [0, 2, 3]  # vendor, table, totals
    for line in label:
        assert all(0.0 <= float(v) <= 1.0 for v in line.split()[1:])
    row = json.loads((tmp_path / "manifest.jsonl").read_text().splitlines()[0])
    assert row["truth"]["vendor_name"] == "ACME TRADERS"
    assert (tmp_path / row["image"]).exists()


def test_yolo_lines_geometry_and_degenerate_boxes():
    lines = services.yolo_lines(
        [
            {"cls": "table", "bbox": [0.1, 0.2, 0.5, 0.4]},
            {"cls": "other", "bbox": [0.1, 0.1, 0.1001, 0.1001]},
            {"cls": "alien", "bbox": [0, 0, 1, 1]},
        ]
    )
    assert lines == ["2 0.300000 0.300000 0.400000 0.200000"]


# ---------------------------------------------------------------- retrain / registry
def prev_new(prev, new):
    def m(v):
        return {"map50": v, "per_class_ap50": {}}

    return {
        "previous": {k: m(v) for k, v in prev.items()},
        "new": {k: m(v) for k, v in new.items()},
    }


def test_compare_recommends_only_safe_improvements():
    both = services.compare(*prev_new({"a": 0.5, "b": 0.5}, {"a": 0.6, "b": 0.5}).values())
    assert both["recommend_activate"] and both["deltas"] == {"a": 0.1, "b": 0.0}
    regress = services.compare(*prev_new({"a": 0.5, "b": 0.5}, {"a": 0.9, "b": 0.45}).values())
    assert not regress["recommend_activate"]  # b dropped 5 points
    flat = services.compare(*prev_new({"a": 0.5}, {"a": 0.5}).values())
    assert not flat["recommend_activate"]  # no improvement anywhere


@pytest.fixture
def weights(tmp_path):
    p = tmp_path / "base.pt"
    p.write_bytes(b"w")
    return p


def test_run_retrain_registers_version_with_comparison(world, doc, weights, tmp_path, settings):
    settings.LAYOUT_MODEL_PATH = str(weights)
    c, d = doc
    c.post(u(world["ws"], d, "approve/"))
    seen = {}

    def runner(args):
        seen.update(args)
        assert Path(args["feedback"], "manifest.jsonl").exists()
        return {
            **prev_new({"synthetic-hard": 0.60}, {"synthetic-hard": 0.66}),
            "weights": str(tmp_path / "new.pt"),
        }

    v = services.run_retrain(epochs=3, runner=runner, work_dir=tmp_path / "w")
    assert seen["base"] == str(weights) and seen["epochs"] == 3
    assert v.n_feedback == 1 and v.metrics["recommend_activate"] is True
    assert v.metrics["deltas"] == {"synthetic-hard": 0.06}
    job = RetrainJob.objects.get()
    assert job.status == "done" and job.result == v
    assert not v.is_active  # never auto-activated


def test_run_retrain_failure_is_recorded(world, doc, weights, tmp_path, settings):
    settings.LAYOUT_MODEL_PATH = str(weights)
    c, d = doc
    c.post(u(world["ws"], d, "approve/"))

    def boom(args):
        raise RuntimeError("out of memory")

    with pytest.raises(RuntimeError):
        services.run_retrain(runner=boom, work_dir=tmp_path / "w")
    job = RetrainJob.objects.get()
    assert job.status == "failed" and "out of memory" in job.log


def test_run_retrain_needs_a_model_and_feedback(world, tmp_path, weights, settings):
    settings.LAYOUT_MODEL_PATH = ""
    with pytest.raises(RuntimeError, match="No current layout model"):
        services.run_retrain(runner=lambda a: {}, work_dir=tmp_path / "a")
    settings.LAYOUT_MODEL_PATH = str(weights)
    with pytest.raises(RuntimeError, match="No approved documents"):
        services.run_retrain(runner=lambda a: {}, work_dir=tmp_path / "b")


def test_activate_rollback_and_get_layout_follow_the_active_model(tmp_path, monkeypatch, settings):
    monkeypatch.undo()  # use the real services.get_layout, not the FakeLayout fixture
    base, new = tmp_path / "base.pt", tmp_path / "new.pt"
    base.write_bytes(b"1")
    new.write_bytes(b"2")
    settings.LAYOUT_MODEL_PATH = str(base)
    v1 = ModelVersion.objects.create(name="v1", path=str(base))
    v2 = ModelVersion.objects.create(name="v2", path=str(new), parent=v1)
    assert pipeline_services.get_layout().weights == str(base)  # default weights
    services.activate(v2)
    assert pipeline_services.get_layout().weights == str(new)
    services.activate(v1)
    assert ModelVersion.objects.filter(is_active=True).count() == 1
    services.activate(v2)
    assert services.rollback().name == "v1"  # parent restored
    assert ModelVersion.objects.get(name="v1").is_active


def test_management_commands_export_and_activate(world, doc, tmp_path, capsys):
    c, d = doc
    c.post(u(world["ws"], d, "approve/"))
    call_command("export_training_data", "--out", str(tmp_path / "fb"))
    assert "exported 1 samples" in capsys.readouterr().out
    ModelVersion.objects.create(name="m1", path="x")
    call_command("activate_model", "m1")
    assert ModelVersion.objects.get(name="m1").is_active
    call_command("activate_model", "--rollback")
    assert not ModelVersion.objects.get(name="m1").is_active


# ---------------------------------------------------------------- admin API
def staff_client(world):
    u_ = world["users"]["member"]
    u_.is_staff = True
    u_.save()
    return client_for(u_)


def test_admin_endpoints_are_staff_only(world):
    for who in ("owner", "member", "viewer"):
        c = client_for(world["users"][who])
        assert c.get("/api/v1/admin/models/").status_code == 403
        assert c.post("/api/v1/admin/retrain/", {}, format="json").status_code == 403
    assert client_for().get("/api/v1/admin/models/").status_code == 401
    assert client_for(api_key=world["raw_key"]).get("/api/v1/admin/models/").status_code == 403


def test_staff_lists_models_and_feedback_counts(world, doc):
    c, d = doc
    c.post(u(world["ws"], d, "approve/"))
    ModelVersion.objects.create(name="m1", path="x", metrics={"deltas": {"a": 0.1}})
    data = staff_client(world).get("/api/v1/admin/models/").json()
    assert data["models"][0]["name"] == "m1"
    assert data["feedback"]["samples"] == 1


def test_staff_activates_and_rolls_back_via_api(world):
    v1 = ModelVersion.objects.create(name="v1", path="a")
    v2 = ModelVersion.objects.create(name="v2", path="b", parent=v1)
    s = staff_client(world)
    assert s.post(f"/api/v1/admin/models/{v2.id}/activate/").json()["is_active"] is True
    assert s.post("/api/v1/admin/models/rollback/").json()["active"]["name"] == "v1"


def test_retrain_endpoint_starts_job_and_blocks_concurrent_runs(world, doc, settings):
    settings.LAYOUT_MODEL_PATH = ""  # eager task runs and fails fast: no base model
    s = staff_client(world)
    no_samples = s.post("/api/v1/admin/retrain/", {"epochs": 2}, format="json")
    assert no_samples.status_code == 400 and "approve" in no_samples.json()["detail"]
    c, d = doc
    c.post(u(world["ws"], d, "approve/"))
    assert s.post("/api/v1/admin/retrain/", {"epochs": "abc"}, format="json").status_code == 400
    res = s.post("/api/v1/admin/retrain/", {"epochs": 2}, format="json")
    assert res.status_code == 202
    job = s.get(f"/api/v1/admin/retrain/{res.json()['id']}/").json()
    assert job["status"] == "failed" and "No current layout model" in job["log"]
    RetrainJob.objects.create(status="running")
    assert s.post("/api/v1/admin/retrain/", {}, format="json").status_code == 400
    assert s.post("/api/v1/admin/retrain/", {"epochs": 99}, format="json").status_code == 400
    assert settings.LLM_PROVIDER == "fake"


def test_subprocess_runner_decodes_utf8_output_and_parses_the_result_line(monkeypatch, tmp_path):
    """Regression: the trainer prints non-cp1252 characters; decoding must not crash on Windows."""
    import subprocess
    import types

    payload = {"previous": {}, "new": {}, "weights": "w.pt"}
    out = "progress \u2501\u2501\u2501 \u2713\nRESULT " + json.dumps(payload) + "\n"
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    got = services.subprocess_runner(
        {"feedback": str(tmp_path), "base": "b.pt", "out": str(tmp_path), "epochs": 1}
    )
    assert got == payload
    assert seen["encoding"] == "utf-8" and seen["env"]["PYTHONIOENCODING"] == "utf-8"
