"""Strict Pydantic schema the LLM must fill. No Django imports: usable from ml/ and tests."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_DOT_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3}){2,}")


def to_number(value):
    """'Rs. 1,180.50' -> 1180.5 ; passes through numbers/None ; unparseable -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value)
    dotted = _DOT_THOUSANDS.search(text)  # 1.346.000 (Indonesian style)
    if dotted:
        return float(dotted.group().replace(".", ""))
    m = _NUM.search(text.replace(",", ""))
    return float(m.group()) if m else None


class LineItem(BaseModel):
    description: str | None = Field(None, description="Item name exactly as printed")
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = Field(None, description="Line total as printed")

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def _num(cls, v):
        return to_number(v)


class InvoiceExtraction(BaseModel):
    """Copy values exactly as printed. Use null when absent. Never compute or guess."""

    vendor_name: str | None = Field(None, description="Seller / shop name")
    ntn: str | None = Field(None, description="Seller NTN as printed")
    strn: str | None = Field(None, description="Sales Tax Registration No (STRN/GST No) as printed")
    invoice_number: str | None = None
    invoice_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    currency: str = Field("PKR", description="3-letter code; PKR if Rs/PKR or unspecified")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = Field(None, description="Amount before sales tax, as printed")
    tax_rate: float | None = Field(None, description="Sales tax percent as printed, e.g. 18")
    sales_tax: float | None = Field(None, description="Sales tax / GST amount as printed")
    total: float | None = Field(None, description="Grand total payable, as printed")

    @field_validator("subtotal", "tax_rate", "sales_tax", "total", mode="before")
    @classmethod
    def _num(cls, v):
        return to_number(v)

    @field_validator("currency", mode="before")
    @classmethod
    def _cur(cls, v):
        return (str(v).strip().upper() if v else "PKR")[:3] or "PKR"


# Scalar fields tracked individually (values, boxes, confidence, review).
SCALAR_FIELDS = [
    "vendor_name",
    "ntn",
    "strn",
    "invoice_number",
    "invoice_date",
    "currency",
    "subtotal",
    "tax_rate",
    "sales_tax",
    "total",
]
NUMERIC_FIELDS = {"subtotal", "tax_rate", "sales_tax", "total"}
REQUIRED_FIELDS = ["vendor_name", "invoice_date", "total"]
