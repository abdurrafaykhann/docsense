import numpy as np
import pytest
from django.core.files.base import ContentFile

from apps.documents.models import Document, Region
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import core
from apps.pipeline.grouping import (
    OTHER_MAX_CHARS,
    assign_words,
    pages_to_prompt_text,
    pages_to_region_prompt_text,
    regions_usable,
)
from apps.pipeline.layout import FakeLayout, keep_best_per_class
from apps.pipeline.layout import Region as LRegion
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.runner import run_pipeline
from apps.pipeline.tests.test_pipeline import GOOD, LINES, png_bytes
from apps.validation.grounding import words_from_lines
from apps.workspaces.models import Workspace

FOOTER = [f"Terms and conditions clause {i} goods once sold" for i in range(1, 25)]
ALL_LINES = [*LINES, *FOOTER]
N = len(ALL_LINES)


def band(first: int, last: int) -> list[float]:
    """Normalised bbox covering text lines first..last (words_from_lines geometry)."""
    return [0.0, first / (N + 1), 1.0, (last + 1) / (N + 1)]


REGIONS = [
    LRegion("vendor", band(0, 1), 0.9),  # name + NTN/STRN
    LRegion("meta", band(2, 3), 0.9),  # invoice no + date
    LRegion("table", band(4, 5), 0.9),  # line items
    LRegion("totals", band(6, 8), 0.9),  # subtotal / tax / total
    LRegion("other", band(9, N - 1), 0.8),  # long footer
]


def words():
    return {1: words_from_lines(ALL_LINES)}


def test_words_are_assigned_to_their_region_and_unassigned_go_to_other():
    groups = assign_words(words()[1], REGIONS)
    texts = {c: " ".join(w.text for w in ws) for c, ws in groups.items()}
    assert "ACME" in texts["vendor"] and "1234567-8" in texts["vendor"]
    assert "INV-0042" in texts["meta"] and "12/03/2024" in texts["meta"]
    assert "Widget" in texts["table"] and "Gadget" in texts["table"]
    assert "3,540.00" in texts["totals"] and "Subtotal" in texts["totals"]
    assert "Terms" in texts["other"]
    stray = assign_words(words()[1], REGIONS[:2])  # only vendor+meta: rest -> other
    assert "3,540.00" in " ".join(w.text for w in stray["other"])


def test_smallest_region_wins_when_regions_overlap():
    big = LRegion("other", [0.0, 0.0, 1.0, 1.0], 0.5)
    groups = assign_words(words()[1], [big, REGIONS[3]])
    assert "3,540.00" in " ".join(w.text for w in groups["totals"])


def test_region_prompt_is_labelled_ordered_and_much_shorter():
    text = pages_to_region_prompt_text(words(), {1: REGIONS}, 12000)
    order = [text.index(f"[{c}]") for c in ("VENDOR", "META", "TABLE", "TOTALS", "OTHER")]
    assert order == sorted(order)
    other = text.split("[OTHER]\n", 1)[1]
    assert len(other) <= OTHER_MAX_CHARS
    assert len(text) < len(pages_to_prompt_text(words(), 12000))  # fewer tokens than whole page


def test_unusable_layout_falls_back_to_whole_page_text():
    only_vendor = [REGIONS[0]]
    assert not regions_usable(only_vendor) and regions_usable(REGIONS)
    assert pages_to_region_prompt_text(words(), {1: only_vendor}, 12000) == pages_to_prompt_text(
        words(), 12000
    )
    assert "[VENDOR]" not in pages_to_region_prompt_text(words(), {}, 12000)


def test_keep_best_per_class_keeps_highest_score_and_all_others():
    regs = [
        LRegion("table", [0, 0.3, 1, 0.5], 0.4),
        LRegion("table", [0, 0.35, 1, 0.55], 0.9),
        LRegion("other", [0, 0.9, 1, 0.95], 0.3),
        LRegion("other", [0, 0.0, 1, 0.05], 0.3),
    ]
    out = keep_best_per_class(regs)
    assert [r.cls for r in out] == ["other", "table", "other"]
    assert next(r for r in out if r.cls == "table").score == 0.9


def test_core_uses_regions_and_reports_layout_step():
    model = FakeChatModel([GOOD])
    llm = LLMClient([Provider("fake", model)])
    steps = []
    img = np.full((60, 40, 3), 255, np.uint8)
    res = core.process(
        [img],
        FakeOCR(ALL_LINES),
        llm,
        clean=False,
        layout=FakeLayout(REGIONS),
        on_step=lambda s, st, d="": steps.append((s, st)),
    )
    assert res.layout_used and ("layout", "done") in steps
    prompt = model.calls[0][1][1]
    assert (
        "[TOTALS]" in prompt and "Total 3,540.00" in prompt.split("[TOTALS]")[1].split("[OTHER]")[0]
    )
    assert set(res.regions_by_page) == {1}


def test_core_without_layout_skips_step_and_uses_whole_page():
    steps = []
    model = FakeChatModel([GOOD])
    img = np.full((60, 40, 3), 255, np.uint8)
    res = core.process(
        [img],
        FakeOCR(LINES),
        LLMClient([Provider("f", model)]),
        clean=False,
        on_step=lambda s, st, d="": steps.append((s, st)),
    )
    assert ("layout", "skipped") in steps and not res.layout_used
    assert "[TOTALS]" not in model.calls[0][1][1]


@pytest.mark.django_db
def test_runner_persists_regions_and_api_returns_them(client):
    ws = Workspace.create_unique("T")
    d = Document(workspace=ws, original_name="r.png", content_type="image/png", size=1, sha256="x")
    d.file.save("r.png", ContentFile(png_bytes()), save=True)
    out = run_pipeline(
        d.id,
        ocr=FakeOCR(ALL_LINES),
        llm=LLMClient([Provider("f", FakeChatModel([GOOD]))]),
        layout=FakeLayout(REGIONS),
    )
    out.refresh_from_db()
    assert out.progress["layout"]["status"] == "done"
    rows = Region.objects.filter(page__document=out)
    assert sorted(r.cls for r in rows) == ["meta", "other", "table", "totals", "vendor"]
    assert all(r.source == "model" for r in rows)
