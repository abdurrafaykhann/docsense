import io

import cv2
import numpy as np
import pytest
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw

from apps.documents.models import Document
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.llm.models import LLMUsage
from apps.pipeline.cleanup import clean_image, estimate_skew
from apps.pipeline.grouping import words_to_lines
from apps.pipeline.ocr import FakeOCR
from apps.pipeline.runner import run_pipeline
from apps.validation.grounding import words_from_lines
from apps.workspaces.models import Workspace

LINES = [
    "ACME TRADERS",
    "NTN 1234567-8 STRN 1234567890123",
    "Invoice No INV-0042",
    "Date 12/03/2024",
    "Widget 2 500.00 1000.00",
    "Gadget 1 2000.00 2000.00",
    "Subtotal 3,000.00",
    "Sales Tax 18% 540.00",
    "Total 3,540.00",
]
GOOD = dict(
    vendor_name="ACME TRADERS",
    ntn="1234567-8",
    strn="1234567890123",
    invoice_number="INV-0042",
    invoice_date="2024-03-12",
    line_items=[
        {"description": "Widget", "quantity": 2, "unit_price": 500, "amount": 1000},
        {"description": "Gadget", "quantity": 1, "unit_price": 2000, "amount": 2000},
    ],
    subtotal=3000,
    tax_rate=18,
    sales_tax=540,
    total=3540,
)


def png_bytes(w=600, h=800):
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    for i in range(12):
        d.text((40, 40 + i * 50), f"line {i} sample receipt text", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def doc(db):
    ws = Workspace.create_unique("T")
    d = Document(workspace=ws, original_name="r.png", content_type="image/png", size=1, sha256="x")
    d.file.save("r.png", ContentFile(png_bytes()), save=True)
    return d


def llm(*script):
    return LLMClient([Provider("fake", FakeChatModel(list(script)))])


def test_clean_invoice_ends_done_with_boxes_and_pages(doc):
    out = run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=llm(GOOD))
    out.refresh_from_db()
    assert out.status == "done" and out.page_count == 1
    ext = out.extractions.get()
    assert not ext.needs_review and ext.issues == [] and ext.overall_confidence > 0.9
    total = ext.fields.get(name="total")
    assert total.value == "3540" and total.bbox and total.confidence > 0.9
    assert out.pages.get().words  # OCR words stored for the viewer
    assert {s["status"] for s in out.progress.values()} <= {"done", "skipped"}
    assert out.progress["layout"]["status"] == "skipped"


def test_arithmetic_error_routes_to_review_and_flags_field(doc):
    out = run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=llm({**GOOD, "total": 3500}))
    out.refresh_from_db()
    assert out.status == "needs_review"
    ext = out.extractions.get()
    assert any(i["code"] == "total_mismatch" for i in ext.issues)
    assert "total_mismatch" in ext.fields.get(name="total").flags


def test_llm_failure_marks_document_failed_with_step(doc):
    out = run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=llm(ValueError("boom")))
    out.refresh_from_db()
    assert out.status == "failed" and out.error.startswith("extract:")
    assert out.progress["extract"]["status"] == "failed"


def test_reprocess_creates_new_version_and_llm_cache_avoids_second_call(doc):
    model = FakeChatModel([GOOD])
    client = LLMClient([Provider("fake", model)])
    run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=client)
    run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=client)
    assert doc.extractions.count() == 2 and len(model.calls) == 1


def test_usage_is_logged_with_workspace_context(doc):
    from apps.llm.client import db_usage_logger

    client = LLMClient([Provider("fake", FakeChatModel([GOOD]))], on_usage=db_usage_logger)
    run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=client)
    row = LLMUsage.objects.get()
    assert row.document_id == doc.id and row.workspace_id == doc.workspace_id
    assert row.status == "ok" and row.prompt_chars > 100


def test_prompt_contains_only_ocr_text_in_reading_order(doc):
    model = FakeChatModel([GOOD])
    run_pipeline(doc.id, ocr=FakeOCR(LINES), llm=LLMClient([Provider("f", model)]))
    prompt = model.calls[0][1][1]
    assert prompt.index("ACME TRADERS") < prompt.index("Total")
    assert "--- page 1 ---" in prompt


# ---- cleanup / grouping -------------------------------------------------------------


def text_page(angle=0.0):
    img = np.full((900, 700, 3), 255, np.uint8)
    for i in range(14):
        cv2.putText(
            img,
            f"ITEM {i} QTY {i} PRICE 100.00",
            (40, 80 + i * 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 0),
            2,
        )
    if angle:
        m = cv2.getRotationMatrix2D((350, 450), angle, 1.0)
        img = cv2.warpAffine(img, m, (700, 900), borderValue=(255, 255, 255))
    return img


def test_skew_estimate_recovers_rotation():
    # rotating a level page by +6 deg should be estimated as ~ -6 (the correction), within 1 deg
    est = estimate_skew(cv2.cvtColor(text_page(6.0), cv2.COLOR_RGB2GRAY))
    assert abs(abs(est) - 6.0) < 1.0
    assert abs(estimate_skew(cv2.cvtColor(text_page(0.0), cv2.COLOR_RGB2GRAY))) < 0.6


def test_deskew_actually_levels_the_page():
    skewed = text_page(7.0)
    fixed, info = clean_image(skewed)
    residual = estimate_skew(cv2.cvtColor(fixed, cv2.COLOR_RGB2GRAY))
    assert abs(residual) < 1.0 and info["deskew_deg"] != 0


def test_words_to_lines_groups_by_row_and_orders_left_to_right():
    words = words_from_lines(["b a", "d c"])
    words.reverse()
    lines = words_to_lines(words)
    assert [[w.text for w in ln] for ln in lines] == [["b", "a"], ["d", "c"]]
