"""Build the committed demo workspace pack: seed/demo_workspace/{images/*.jpg, manifest.json}.

    python -m docsense_ml.synth.demo_pack --out seed/demo_workspace

50 documents from 7 recurring vendors over ~8 months (so analytics have history), with planted,
documented anomalies so every flag type has something to show:

    price_creep     vendor 0: latest cooking-oil price +35%
    amount_outlier  vendor 1: one invoice with 8x quantities
    exact_dup       vendor 2: byte-identical copy of an earlier invoice
    near_dup        vendor 3: same amount, new number, next day
    review queue    3 documents whose extracted total is wrong (a human must fix them)

The manifest stores everything the seed command needs to skip OCR/LLM: word boxes, region boxes,
field boxes and the truth, all taken from the DOM at render time.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from .generator import InvoiceData, make_invoice
from .providers import CATALOG
from .render import Renderer

START = date(2025, 1, 15)
VENDORS = 7
PER_VENDOR = 6  # plus extras below -> 50 documents


def _round5(v: float) -> float:
    return float(round(v / 5) * 5)


def profile(i: int) -> InvoiceData:
    """A stable vendor identity + 3 recurring items, derived from the generator."""
    base = make_invoice(900 + i * 13)
    rng = np.random.default_rng(i)
    cat = CATALOG[base.category]
    picks = [cat[k] for k in rng.choice(len(cat), size=min(3, len(cat)), replace=False)]
    items = [
        {
            "description": d,
            "quantity": 1,
            "unit": u,
            "unit_price": _round5((lo + hi) / 2),
            "amount": 0.0,
        }
        for d, u, lo, hi in picks
    ]
    return dataclasses.replace(base, line_items=items)


def invoice_for(
    prof: InvoiceData, n: int, when: date, rng, *, qty_mult=1, price_bump=None
) -> InvoiceData:
    items = []
    for k, it in enumerate(prof.line_items):
        price = _round5(it["unit_price"] * (1 + rng.uniform(-0.03, 0.03)))
        if price_bump and k == 0:
            price = _round5(it["unit_price"] * price_bump)
        qty = int(rng.integers(1, 5)) * qty_mult
        items.append({**it, "quantity": qty, "unit_price": price, "amount": round(qty * price, 2)})
    subtotal = round(sum(i["amount"] for i in items), 2)
    tax = round(subtotal * prof.tax_rate / 100, 2)
    return dataclasses.replace(
        prof,
        invoice_number=f"{prof.invoice_number.split('-')[0]}-{prof.vendor_name[:2].upper()}{n:04d}",
        invoice_date=when.isoformat(),
        line_items=items,
        subtotal=subtotal,
        sales_tax=tax,
        total=round(subtotal + tax, 2),
    )


def build_pack(out: Path, seed: int = 7, scale: float = 1.5) -> list[dict]:
    out = Path(out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    profiles = [profile(i) for i in range(VENDORS)]
    plan: list[tuple[InvoiceData, str | None]] = []
    for vi, prof in enumerate(profiles):
        for k in range(PER_VENDOR):
            when = START + timedelta(days=int(k * 31 + rng.integers(0, 5)))
            bump = 1.35 if (vi == 0 and k == PER_VENDOR - 1) else None  # price creep
            mult = 8 if (vi == 1 and k == 4) else 1  # amount outlier
            planted = "price_creep" if bump else ("amount_outlier" if mult > 1 else None)
            plan.append(
                (invoice_for(prof, k + 1, when, rng, price_bump=bump, qty_mult=mult), planted)
            )
    # a later invoice for six vendors: 42 + 6 + near-dup + exact-dup = 50 documents
    for vi in (1, 2, 3, 4, 5, 6):
        plan.append(
            (invoice_for(profiles[vi], PER_VENDOR + 1, START + timedelta(days=210), rng), None)
        )
    near_src = next(inv for inv, _ in plan if inv.vendor_name == profiles[3].vendor_name)
    plan.append(
        (
            dataclasses.replace(
                near_src,
                invoice_number=near_src.invoice_number + "-R",
                invoice_date=(
                    date.fromisoformat(near_src.invoice_date) + timedelta(days=1)
                ).isoformat(),
            ),
            "near_dup",
        )
    )
    # review-queue documents: the *extracted* total will be wrong for these
    wrong_total = {len(plan) - 1 - j for j in (1, 6, 11)}

    rows: list[dict] = []
    jpeg: dict[int, bytes] = {}
    with Renderer(scale=scale) as renderer:
        for idx, (inv, planted) in enumerate(plan):
            r = renderer.render(inv)
            buf = io.BytesIO()
            Image.fromarray(r.image).save(buf, "JPEG", quality=82)
            jpeg[idx] = buf.getvalue()
            name = f"demo-{idx + 1:03d}.jpg"
            (out / "images" / name).write_bytes(jpeg[idx])
            rows.append(
                {
                    "file": f"images/{name}", "name": name, "template": inv.template,
                    "category": inv.category, "planted": planted, "truth": inv.truth(),
                    "words": r.words, "fields": r.fields, "regions": r.regions,
                    "extracted_total_wrong": idx in wrong_total,
                }
            )  # fmt: skip
    # byte-identical duplicate of an earlier invoice (vendor 2)
    src_idx = next(
        i for i, (inv, _) in enumerate(plan) if inv.vendor_name == profiles[2].vendor_name and i > 2
    )
    name = f"demo-{len(rows) + 1:03d}.jpg"
    (out / "images" / name).write_bytes(jpeg[src_idx])
    dup = json.loads(json.dumps(rows[src_idx]))
    dup.update(file=f"images/{name}", name=name, planted="exact_dup", extracted_total_wrong=False)
    rows.append(dup)
    (out / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="seed/demo_workspace")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rows = build_pack(Path(a.out), a.seed)
    planted = [r["planted"] for r in rows if r["planted"]]
    print(len(rows), "documents; planted:", planted)


if __name__ == "__main__":
    main()
