import json

import pytest
from django.core.management import call_command

from apps.evaluation.models import EvalRun
from conftest import client_for

pytestmark = pytest.mark.django_db

PAYLOAD = {
    "kind": "extraction",
    "dataset": "cord",
    "arm": "regex",
    "n": 2,
    "git_sha": "abc123",
    "created_at": "2025-01-02T03:04:05+00:00",
    "ocr": "doctr",
    "metrics": {"micro": {"f1": 0.5}, "total_exact_match": 0.5, "review_rate": 0.25},
    "docs": [
        {
            "id": "d0",
            "needs_review": True,
            "issues": ["total_mismatch"],
            "error": None,
            "pred": {"total": 1},
            "score": {"fields": {"total": {"tp": 0, "pred": 1, "truth": 1}}},
        }
    ],
}


@pytest.fixture
def results_file(tmp_path):
    p = tmp_path / "cord-regex.json"
    p.write_text(json.dumps(PAYLOAD))
    return p


def test_import_is_idempotent(results_file):
    call_command("import_eval", str(results_file))
    call_command("import_eval", str(results_file))
    run = EvalRun.objects.get()
    assert (run.kind, run.dataset, run.arm, run.n) == ("extraction", "cord", "regex", 2)
    assert run.docs[0]["wrong_fields"] == ["total"] and "pred" not in run.docs[0]


def test_api_lists_and_details_runs_for_signed_in_users(world, results_file):
    call_command("import_eval", str(results_file))
    c = client_for(world["users"]["viewer"])
    rows = c.get("/api/v1/evaluation/runs/").json()
    assert rows[0]["metrics"]["total_exact_match"] == 0.5 and "docs" not in rows[0]
    detail = c.get(f"/api/v1/evaluation/runs/{rows[0]['id']}/").json()
    assert detail["docs"][0]["issues"] == ["total_mismatch"]
    assert c.get("/api/v1/evaluation/runs/?kind=rag").json() == []


def test_api_rejects_anonymous_and_api_keys(world, results_file):
    call_command("import_eval", str(results_file))
    assert client_for().get("/api/v1/evaluation/runs/").status_code == 401
    assert client_for(api_key=world["raw_key"]).get("/api/v1/evaluation/runs/").status_code == 403
