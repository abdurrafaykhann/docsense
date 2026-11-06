"""Real-browser rendering + dataset build. Needs Microsoft Edge/Chromium (Playwright)."""

import pytest

from docsense_ml.evalset import load_set
from docsense_ml.synth.build import build
from docsense_ml.synth.generator import TEMPLATES, make_invoice
from docsense_ml.synth.render import Renderer

pytestmark = pytest.mark.slow


def test_rendered_boxes_words_and_fields_are_exact():
    with Renderer() as r:
        for i, tpl in enumerate(TEMPLATES):
            inv = make_invoice(900 + i, tpl)
            out = r.render(inv)
            h, w = out.image.shape[:2]
            assert h > 200 and w > 300
            classes = [reg["cls"] for reg in out.regions]
            assert {"vendor", "meta", "table", "totals", "other"} <= set(classes), tpl
            for reg in out.regions:
                x0, y0, x1, y1 = reg["bbox"]
                assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1, (tpl, reg)
            # totals region sits below the table region, vendor above meta
            by = {reg["cls"]: reg["bbox"] for reg in out.regions if reg["cls"] != "other"}
            assert by["totals"][1] >= by["table"][1] and by["vendor"][1] <= by["meta"][1] + 0.3
            text = " ".join(wd["text"] for wd in out.words)
            assert f"{inv.total:,.2f}" in text and inv.ntn in text and inv.strn in text
            # the 'total' field box contains the total's word box
            fx0, fy0, fx1, fy1 = out.fields["total"]
            hit = [wd for wd in out.words if wd["text"] == f"{inv.total:,.2f}"]
            assert any(
                fx0 - 1e-3 <= wd["bbox"][0]
                and wd["bbox"][2] <= fx1 + 1e-3
                and fy0 - 1e-3 <= wd["bbox"][1]
                and wd["bbox"][3] <= fy1 + 1e-3
                for wd in hit
            ), tpl


def test_build_writes_yolo_dataset_and_eval_set(tmp_path):
    counts = build(tmp_path, n=12, seed=1, aug="full", aug_per_image=2)
    assert counts["val"] == 2 and counts["train"] == 20  # i=0,10 are val; 10 train x 2 variants
    imgs = sorted((tmp_path / "images" / "train").glob("*.jpg"))
    labels = sorted((tmp_path / "labels" / "train").glob("*.txt"))
    assert [p.stem for p in imgs] == [p.stem for p in labels]
    for lab in labels:
        for line in lab.read_text().splitlines():
            c, *vals = line.split()
            assert 0 <= int(c) <= 4 and all(0.0 <= float(v) <= 1.0 for v in vals)
    assert "names:" in (tmp_path / "data.yaml").read_text()
    samples = load_set(tmp_path / "eval")
    assert len(samples) == 2 and samples[0].truth["total"] > 0
    assert samples[0].load_image().ndim == 3
