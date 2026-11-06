"""Validation rules in code, not in the LLM. Every failed rule names the fields it implicates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .schema import REQUIRED_FIELDS, InvoiceExtraction

DEFAULT_TAX_RATE = 18.0
# Federal GST and common provincial rates on services (configurable, see PLAN D9).
KNOWN_TAX_RATES = {0.0, 5.0, 13.0, 15.0, 16.0, 17.0, 18.0}
MAX_AGE_DAYS = 365 * 10


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    fields: tuple[str, ...]
    severity: str = "error"  # error | warn

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "fields": list(self.fields),
            "severity": self.severity,
        }


def close(a: float, b: float, abs_tol: float = 1.0, rel_tol: float = 0.005) -> bool:
    """Equal within Rs 1 or 0.5% (rounding on printed receipts)."""
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


# --- tax registration formats -------------------------------------------------
def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def is_valid_ntn(value: str) -> bool:
    """NTN: 7 digits, optionally followed by a check digit (7-1), or a 13-digit CNIC-based NTN."""
    d = _digits(value)
    if len(d) not in (7, 8, 13):
        return False
    return bool(re.fullmatch(r"[\d\- ]+", value.strip()))


def is_valid_strn(value: str) -> bool:
    """STRN: 13 digits, or legacy 17-digit form NN-NN-NNNN-NNN-NN."""
    d = _digits(value)
    return len(d) in (13, 17) and bool(re.fullmatch(r"[\d\- ]+", value.strip()))


# --- date -----------------------------------------------------------------------
def parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def validate(inv: InvoiceExtraction, *, today: date | None = None) -> list[Issue]:
    today = today or date.today()
    issues: list[Issue] = []

    # required fields
    for name in REQUIRED_FIELDS:
        if getattr(inv, name) in (None, ""):
            issues.append(Issue("missing_field", f"{name} not found", (name,)))

    # line items: qty x unit price = amount
    for i, li in enumerate(inv.line_items):
        if None not in (li.quantity, li.unit_price, li.amount) and not close(
            li.quantity * li.unit_price, li.amount
        ):
            issues.append(
                Issue(
                    "line_math",
                    f"Line {i + 1}: {li.quantity} x {li.unit_price} != {li.amount}",
                    ("line_items",),
                )
            )

    # sum of lines = subtotal
    amounts = [li.amount for li in inv.line_items if li.amount is not None]
    if amounts and inv.subtotal is not None and not close(sum(amounts), inv.subtotal):
        issues.append(
            Issue(
                "subtotal_mismatch",
                f"Line items sum to {sum(amounts):.2f} but subtotal is {inv.subtotal:.2f}",
                ("line_items", "subtotal"),
            )
        )

    # tax = subtotal x rate
    rate = inv.tax_rate if inv.tax_rate is not None else DEFAULT_TAX_RATE
    if inv.tax_rate is not None and inv.tax_rate not in KNOWN_TAX_RATES:
        issues.append(
            Issue("unusual_tax_rate", f"Unusual tax rate {inv.tax_rate}%", ("tax_rate",), "warn")
        )
    if inv.subtotal is not None and inv.sales_tax is not None:
        expected = inv.subtotal * rate / 100
        if not close(expected, inv.sales_tax):
            issues.append(
                Issue(
                    "tax_mismatch",
                    f"Sales tax {inv.sales_tax:.2f} != {rate:g}% of {inv.subtotal:.2f} "
                    f"(expected {expected:.2f})",
                    ("sales_tax", "tax_rate", "subtotal"),
                )
            )

    # total = subtotal + tax
    if inv.total is not None and inv.subtotal is not None:
        expected_total = inv.subtotal + (inv.sales_tax or 0.0)
        if not close(expected_total, inv.total):
            issues.append(
                Issue(
                    "total_mismatch",
                    f"Total {inv.total:.2f} != subtotal + tax ({expected_total:.2f})",
                    ("total", "subtotal", "sales_tax"),
                )
            )

    # registration numbers
    if inv.ntn and not is_valid_ntn(inv.ntn):
        issues.append(Issue("bad_ntn", f"'{inv.ntn}' is not a valid NTN format", ("ntn",)))
    if inv.strn and not is_valid_strn(inv.strn):
        issues.append(Issue("bad_strn", f"'{inv.strn}' is not a valid STRN format", ("strn",)))

    # date
    if inv.invoice_date:
        d = parse_iso_date(inv.invoice_date)
        if d is None:
            issues.append(
                Issue("bad_date", f"'{inv.invoice_date}' is not a valid date", ("invoice_date",))
            )
        elif d > today:
            issues.append(Issue("future_date", "Invoice date is in the future", ("invoice_date",)))
        elif d < today - timedelta(days=MAX_AGE_DAYS):
            issues.append(
                Issue("old_date", "Invoice is older than 10 years", ("invoice_date",), "warn")
            )

    if not re.fullmatch(r"[A-Z]{3}", inv.currency):
        issues.append(
            Issue("bad_currency", f"Bad currency '{inv.currency}'", ("currency",), "warn")
        )

    return issues
