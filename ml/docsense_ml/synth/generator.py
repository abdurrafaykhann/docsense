"""Deterministic synthetic invoice data. Arithmetic is always consistent (validators pass)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker

from .providers import PakistaniProvider

TAX_RATES = [18.0] * 8 + [16.0, 13.0]  # federal GST mostly; PRA / SRB for services
TEMPLATES = ["thermal", "fbr_tax", "gst_retail", "pos_compact", "wholesale", "service_urdu"]

# Which templates are natural for which category (others still allowed, just rarer)
PREFERRED = {
    "grocery": ["thermal", "pos_compact", "gst_retail"],
    "electronics": ["gst_retail", "fbr_tax", "wholesale"],
    "pharmacy": ["thermal", "gst_retail", "pos_compact"],
    "hardware": ["wholesale", "fbr_tax"],
    "restaurant": ["thermal", "pos_compact"],
    "services": ["service_urdu", "fbr_tax"],
}


@dataclass
class InvoiceData:
    template: str
    category: str
    vendor_name: str
    vendor_urdu: str
    address: str
    phone: str
    ntn: str
    strn: str
    invoice_number: str
    invoice_date: str  # ISO
    customer: str
    customer_ntn: str
    payment: str
    line_items: list[dict]
    subtotal: float
    tax_rate: float
    sales_tax: float
    total: float
    currency: str = "PKR"
    style: dict = field(default_factory=dict)

    def truth(self) -> dict:
        """Ground truth in the shape of apps.validation.schema.InvoiceExtraction."""
        return {
            "vendor_name": self.vendor_name,
            "ntn": self.ntn,
            "strn": self.strn,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "currency": self.currency,
            "subtotal": self.subtotal,
            "tax_rate": self.tax_rate,
            "sales_tax": self.sales_tax,
            "total": self.total,
            "line_items": [
                {
                    "description": li["description"],
                    "quantity": li["quantity"],
                    "unit_price": li["unit_price"],
                    "amount": li["amount"],
                }
                for li in self.line_items
            ],
        }


def make_faker(seed: int) -> tuple[Faker, random.Random]:
    fake = Faker("en_US")
    fake.add_provider(PakistaniProvider)
    fake.seed_instance(seed)
    fake.random.seed(seed)
    return fake, fake.random


def make_invoice(seed: int, template: str | None = None, today: date | None = None) -> InvoiceData:
    fake, r = make_faker(seed)
    today = today or date(2025, 6, 30)
    category = fake.category()
    template = template or (
        r.choice(PREFERRED[category]) if r.random() < 0.75 else r.choice(TEMPLATES)
    )
    name, urdu = fake.business(category)
    catalogue = fake.catalog(category)

    items = []
    for desc, unit, lo, hi in r.sample(catalogue, k=min(len(catalogue), r.randint(1, 6))):
        qty = r.choice([1, 1, 2, 3, 5]) if unit != "kg" else r.choice([1, 2, 2.5, 5])
        if unit == "hr":
            qty = r.choice([2, 4, 8, 10])
        unit_price = float(
            round(r.uniform(lo, hi) / (5 if hi > 100 else 1)) * (5 if hi > 100 else 1)
        )
        items.append(
            {
                "description": desc,
                "quantity": qty,
                "unit": unit,
                "unit_price": unit_price,
                "amount": round(qty * unit_price, 2),
            }
        )
    subtotal = round(sum(i["amount"] for i in items), 2)
    rate = r.choice(TAX_RATES if category != "services" else [16.0, 13.0, 18.0])
    tax = round(subtotal * rate / 100, 2)
    d = today - timedelta(days=r.randint(0, 900))
    return InvoiceData(
        template=template,
        category=category,
        vendor_name=name,
        vendor_urdu=urdu,
        address=fake.address(),
        phone=fake.phone_pk(),
        ntn=fake.ntn(),
        strn=fake.strn(),
        invoice_number=r.choice(["INV", "SI", "RCP", "BL"]) + f"-{r.randint(1, 99999):05d}",
        invoice_date=d.isoformat(),
        customer=fake.company() if r.random() < 0.5 else fake.name(),
        customer_ntn=fake.ntn(),
        payment=r.choice(["Cash", "Card", "Bank Transfer", "Cheque", "Easypaisa", "JazzCash"]),
        line_items=items,
        subtotal=subtotal,
        tax_rate=rate,
        sales_tax=tax,
        total=round(subtotal + tax, 2),
        style={
            "accent": r.choice(["#1d4ed8", "#047857", "#b91c1c", "#7c3aed", "#111827", "#c2410c"]),
            "font": r.choice(["Arial", "Verdana", "Tahoma", "Times New Roman", "Georgia"]),
            "mono": r.choice(["Courier New", "Consolas", "Lucida Console"]),
            "size": r.choice([12, 13, 14, 15]),
            "money": r.choice(["plain", "rs", "pkr"]),
            "date_fmt": r.choice(["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d.%m.%Y", "%d %B %Y"]),
        },
    )
