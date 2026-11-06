import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "readme_tables.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("readme_tables", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def write(d: Path, name: str, payload: dict):
    (d / name).write_text(json.dumps(payload), encoding="utf-8")


def layout(exp, dataset, map50, per):
    return {
        "kind": "layout",
        "dataset": dataset,
        "arm": f"exp-{exp}: desc {exp}",
        "n": 5,
        "metrics": {"map50": map50, "per_class_ap50": per},
    }


def test_tables_are_rendered_from_result_files(tmp_path, mod):
    full = {c: 0.9 for c in mod.CLASSES}
    write(tmp_path, "a.json", layout("a", "synthetic-hard", 0.5, full))
    write(
        tmp_path,
        "b.json",
        layout("a", "cord-real-test", 0.1, {"table": 0.12, "totals": 0.08, "vendor": None}),
    )
    write(
        tmp_path,
        "c.json",
        {
            "kind": "rag",
            "dataset": "demo",
            "arm": "retrieval",
            "n": 48,
            "metrics": {"hit_at_5": 1.0, "mrr": 0.85, "unanswerable_rejected_by_gate": 0.83},
        },
    )
    block = mod.render(tmp_path)
    assert "| **exp-a**: desc a | 50.0% | **10.0%** | 12.0% | 8.0% |" in block
    assert "| exp-a | 90.0% | 90.0% | 90.0% | 90.0% | 90.0% |" in block
    assert (
        "| retrieval | 48 | 100.0% | 0.85 | 83.0% | pending (needs API keys) | pending | pending |"
        in block
    )
    assert "_No extraction runs yet._" in block


def test_splice_replaces_only_the_marked_block_and_check_detects_drift(tmp_path, mod):
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n{mod.START}\nstale\n{mod.END}\nfooter\n", encoding="utf-8")
    results = tmp_path / "res"
    results.mkdir()
    new = mod.splice(readme.read_text(encoding="utf-8"), mod.render(results))
    assert new.startswith("# Title\n") and new.endswith("\nfooter\n") and "stale" not in new
    assert mod.splice(new, mod.render(results)) == new  # idempotent
    with pytest.raises(SystemExit):
        mod.splice("no markers here", "x")
