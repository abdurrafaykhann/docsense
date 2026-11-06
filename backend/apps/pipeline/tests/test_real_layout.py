"""Real models end to end: my trained YOLO + docTR on a seeded demo document.

pytest -m slow --force-enable-socket apps/pipeline/tests/test_real_layout.py
"""

import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import core
from apps.pipeline.layout import YoloLayoutDetector
from apps.pipeline.loader import load_pages

pytestmark = [pytest.mark.slow, pytest.mark.enable_socket]

WEIGHTS = Path(settings.BASE_DIR).parent / "ml" / "models" / "layout-current.pt"
PACK = Path(settings.BASE_DIR).parent / "seed" / "demo_workspace"


@pytest.fixture(scope="module")
def sample():
    pytest.importorskip("ultralytics")
    if not WEIGHTS.exists():
        pytest.skip("ml/models/layout-current.pt not present")
    rows = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    row = next(r for r in rows if r["truth"]["total"] > 0 and not r["planted"])
    img = load_pages((PACK / row["file"]).read_bytes(), "image/jpeg")[0]
    return row, img


def test_trained_model_finds_ordered_regions_on_a_demo_invoice(sample):
    row, img = sample
    regions = {r.cls: r for r in YoloLayoutDetector(WEIGHTS).detect(img)}
    assert {"vendor", "table", "totals"} <= set(regions), sorted(regions)
    assert regions["vendor"].bbox[1] < regions["table"].bbox[1] < regions["totals"].bbox[1]
    assert regions["totals"].score > 0.5


def test_region_text_reaches_the_llm_with_the_total_in_the_totals_section(sample):
    pytest.importorskip("doctr")
    from apps.pipeline.ocr import DocTROCR

    row, img = sample
    model = FakeChatModel([{"total": row["truth"]["total"]}])
    res = core.process(
        [img], DocTROCR(), LLMClient([Provider("f", model)]), layout=YoloLayoutDetector(WEIGHTS)
    )
    assert res.layout_used
    prompt = model.calls[0][1][1]
    totals_section = prompt.split("[TOTALS]")[1].split("[OTHER]")[0]
    assert f"{row['truth']['total']:,.2f}".split(".")[0] in totals_section
