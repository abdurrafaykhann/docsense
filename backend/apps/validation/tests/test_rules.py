from datetime import date

import pytest

from apps.validation.rules import close, is_valid_ntn, is_valid_strn, validate
from apps.validation.schema import InvoiceExtraction, LineItem, to_number

TODAY = date(2025, 6, 1)


def good(**over):
    base = dict(
        vendor_name="ACME Traders",
        ntn="1234567-8",
        strn="1234567890123",
        invoice_number="INV-1",
        invoice_date="2025-05-20",
        line_items=[
            LineItem(description="A", quantity=2, unit_price=500, amount=1000),
            LineItem(description="B", quantity=1, unit_price=2000, amount=2000),
        ],
        subtotal=3000,
        tax_rate=18,
        sales_tax=540,
        total=3540,
    )
    base.update(over)
    return InvoiceExtraction(**base)


def codes(inv):
    return {i.code for i in validate(inv, today=TODAY)}


def test_clean_invoice_has_no_issues():
    assert validate(good(), today=TODAY) == []


def test_line_math_failure():
    inv = good(
        line_items=[LineItem(quantity=2, unit_price=500, amount=900)],
        subtotal=900,
        sales_tax=162,
        total=1062,
    )
    assert codes(inv) == {"line_math"}


def test_subtotal_mismatch_names_both_fields():
    issues = validate(good(subtotal=2500, sales_tax=450, total=2950), today=TODAY)
    sub = next(i for i in issues if i.code == "subtotal_mismatch")
    assert set(sub.fields) == {"line_items", "subtotal"}


def test_tax_default_rate_18_and_stated_rate():
    assert "tax_mismatch" in codes(good(tax_rate=None, sales_tax=300, total=3300))
    # stated 16% (e.g. PRA) is respected
    assert codes(good(tax_rate=16, sales_tax=480, total=3480)) == set()


def test_unusual_rate_is_warning_not_error():
    issues = validate(good(tax_rate=7, sales_tax=210, total=3210), today=TODAY)
    assert [(i.code, i.severity) for i in issues] == [("unusual_tax_rate", "warn")]


def test_total_mismatch():
    assert codes(good(total=3600)) == {"total_mismatch"}


def test_rounding_tolerance():
    assert close(100.0, 100.9) and not close(100.0, 102.5)
    assert codes(good(sales_tax=540.6, total=3540.6)) == set()


@pytest.mark.parametrize(
    "v,ok",
    [
        ("1234567", True),
        ("1234567-8", True),
        ("1234567-89", False),
        ("12345", False),
        ("35202-1234567-1", True),
        ("12AB567", False),
    ],
)
def test_ntn_formats(v, ok):
    assert is_valid_ntn(v) is ok


@pytest.mark.parametrize(
    "v,ok",
    [
        ("1234567890123", True),
        ("12-34-5678-901-23", True),
        ("123456", False),
        ("12345678901234", False),
    ],
)
def test_strn_formats(v, ok):
    assert is_valid_strn(v) is ok


def test_bad_registration_numbers_flagged():
    assert codes(good(ntn="123", strn="99")) == {"bad_ntn", "bad_strn"}


def test_date_rules():
    assert codes(good(invoice_date="2025-13-40")) == {"bad_date"}
    assert codes(good(invoice_date="2025-06-02")) == {"future_date"}
    assert "old_date" in codes(good(invoice_date="2010-01-01"))


def test_missing_required_fields():
    inv = good(vendor_name=None, invoice_date=None, total=None)
    assert [i.fields for i in validate(inv, today=TODAY) if i.code == "missing_field"] == [
        ("vendor_name",),
        ("invoice_date",),
        ("total",),
    ]


def test_number_coercion_from_llm_strings():
    assert to_number("Rs. 1,180.50") == 1180.5
    assert to_number("N/A") is None
    inv = InvoiceExtraction(total="PKR 3,540", sales_tax="540.00", line_items=[{"amount": "1,000"}])
    assert inv.total == 3540 and inv.line_items[0].amount == 1000
