from apps.validation.grounding import locate, words_from_lines
from apps.validation.rules import validate
from apps.validation.schema import InvoiceExtraction, LineItem
from apps.validation.scoring import needs_review, overall_confidence, score_fields

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
WORDS = words_from_lines(LINES)


def inv(**over):
    base = dict(
        vendor_name="ACME TRADERS",
        ntn="1234567-8",
        strn="1234567890123",
        invoice_number="INV-0042",
        invoice_date="2024-03-12",
        line_items=[
            LineItem(description="Widget", quantity=2, unit_price=500, amount=1000),
            LineItem(description="Gadget", quantity=1, unit_price=2000, amount=2000),
        ],
        subtotal=3000,
        tax_rate=18,
        sales_tax=540,
        total=3540,
    )
    base.update(over)
    return InvoiceExtraction(**base)


def run(i):
    from datetime import date

    issues = validate(i, today=date(2025, 1, 1))
    return issues, score_fields(i, issues, WORDS)


def test_locate_finds_values_with_boxes():
    assert locate("total", 3540.0, WORDS).bbox[1] > locate("subtotal", 3000.0, WORDS).bbox[1]
    assert locate("invoice_date", "2024-03-12", WORDS) is not None
    assert locate("ntn", "1234567-8", WORDS) is not None
    assert locate("vendor_name", "Acme Traders", WORDS).match >= 0.85
    assert locate("vendor_name", "Totally Other Shop", WORDS) is None
    assert locate("total", 9999.0, WORDS) is None


def test_clean_invoice_is_not_sent_to_review():
    issues, scores = run(inv())
    assert issues == [] and not needs_review(scores, issues)
    assert overall_confidence(scores) > 0.9


def test_arithmetic_error_flags_fields_and_routes_to_review():
    issues, scores = run(inv(total=3500))
    by = {s.name: s for s in scores}
    assert "total_mismatch" in by["total"].flags and by["total"].confidence < 0.7
    assert needs_review(scores, issues)


def test_hallucinated_value_not_in_ocr_is_flagged():
    issues, scores = run(inv(vendor_name="Phantom Enterprises"))
    v = next(s for s in scores if s.name == "vendor_name")
    assert "not_in_ocr" in v.flags and v.confidence <= 0.6
    assert needs_review(scores, issues)


def test_missing_required_field_routes_to_review():
    issues, scores = run(inv(invoice_date=None))
    assert needs_review(scores, issues)
