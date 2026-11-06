from datetime import date, timedelta

import numpy as np
import pytest

from apps.analytics.detectors import (
    FlagSpec,
    InvoiceRow,
    ItemRow,
    find_duplicates,
    hamming,
    isolation_outliers,
    item_key,
    merge_outliers,
    modified_z_scores,
    price_creep,
    robust_outliers,
)

D0 = date(2025, 3, 1)


def row(i, vendor=1, number="", d=D0, total=1000.0, **kw):
    return InvoiceRow(i, vendor, number, d, total, **kw)


# ---------------------------------------------------------------- duplicates
def test_exact_duplicate_by_vendor_and_invoice_number_flags_the_later_document():
    flags = find_duplicates([row(1, number="INV-001"), row(2, number="inv 001", total=5.0)])
    assert [(f.document_id, f.kind) for f in flags] == [(2, "exact_dup")]
    assert flags[0].evidence["duplicate_of"] == 1


def test_identical_file_hash_is_exact_even_for_different_vendors():
    flags = find_duplicates([row(1, vendor=1, sha256="ab"), row(2, vendor=2, sha256="ab")])
    assert flags[0].kind == "exact_dup" and flags[0].evidence["reason"] == "identical file"


def test_near_duplicate_needs_same_vendor_amount_and_close_dates():
    close = find_duplicates([row(1), row(2, d=D0 + timedelta(days=2), number="X")])
    assert [f.kind for f in close] == ["near_dup"]
    assert find_duplicates([row(1), row(2, d=D0 + timedelta(days=10))]) == []
    assert find_duplicates([row(1), row(2, total=1001.0)]) == []
    assert find_duplicates([row(1, vendor=1), row(2, vendor=2)]) == []  # other vendor


def test_image_duplicate_uses_perceptual_hash_distance_and_weakest_precedence():
    a, b = "ffff0000ffff0000", "ffff0000ffff0007"  # 3 bits apart
    assert hamming(a, b) == 3
    flags = find_duplicates(
        [row(1, vendor=1, phash=a, total=10), row(2, vendor=2, phash=b, total=99)]
    )
    assert flags[0].kind == "image_dup"
    far = "0000ffff0000ffff"
    assert find_duplicates([row(1, phash=a, total=1), row(2, vendor=2, phash=far, total=2)]) == []
    # a pair that is both a near and an image duplicate is reported as the stronger 'near_dup'
    both = find_duplicates([row(1, phash=a), row(2, phash=b)])
    assert [f.kind for f in both] == ["near_dup"]


# ---------------------------------------------------------------- outliers
def vendor_series(n=12, base=1000.0, seed=0, vendor=1, start=100):
    rng = np.random.default_rng(seed)
    return [
        row(start + i, vendor=vendor, total=float(base * rng.uniform(0.9, 1.1)), number=f"N{i}",
            d=D0 + timedelta(days=i * 20))
        for i in range(n)
    ]  # fmt: skip


def test_modified_z_is_robust_to_the_outlier_itself():
    z = modified_z_scores(np.array([10, 11, 9, 10, 10.5, 9.5, 100.0]))
    assert z[-1] > 20 and np.all(np.abs(z[:-1]) < 2)
    assert np.all(modified_z_scores(np.array([5.0, 5.0, 5.0])) == 0)  # no spread, no outliers


def test_robust_outlier_flags_a_spike_but_not_normal_variation_or_thin_history():
    rows = [*vendor_series(), row(999, total=9500.0, number="BIG")]
    flags = robust_outliers(rows)
    assert [f.document_id for f in flags] == [999]
    assert flags[0].evidence["direction"] == "high" and flags[0].severity == "high"
    assert robust_outliers(vendor_series()) == []
    assert robust_outliers([*vendor_series(3), row(999, total=99999.0)]) == []  # < 5 invoices
    low = robust_outliers([*vendor_series(), row(998, total=40.0)])
    assert low and low[0].evidence["direction"] == "low"


def test_isolation_forest_catches_odd_tax_ratio_that_totals_alone_miss():
    rows = []
    for v in range(1, 6):
        for r in vendor_series(14, base=800.0 * v, seed=v, vendor=v, start=v * 100):
            r.subtotal = r.total / 1.18
            r.sales_tax = r.total - r.subtotal
            r.n_items = 3
            rows.append(r)
    weird = row(5000, vendor=1, total=800.0, subtotal=800.0, sales_tax=0.0, n_items=40)
    rows.append(weird)
    flagged = {f.document_id for f in isolation_outliers(rows)}
    assert 5000 in flagged and len(flagged) <= 6  # contamination keeps it selective
    assert isolation_outliers(rows[:10]) == []  # too little data for a workspace model


def test_merge_outliers_unions_methods_and_keeps_highest_severity():
    a = FlagSpec(1, "amount_outlier", "medium", {"method": "robust_z", "z": 4.0})
    b = FlagSpec(1, "amount_outlier", "high", {"method": "isolation_forest", "score": -0.7})
    c = FlagSpec(2, "amount_outlier", "medium", {"method": "isolation_forest", "score": -0.6})
    merged = {m.document_id: m for m in merge_outliers([a], [b, c])}
    assert merged[1].evidence["methods"] == ["robust_z", "isolation_forest"]
    assert merged[1].severity == "high" and merged[1].evidence["z"] == 4.0
    assert merged[2].evidence["methods"] == ["isolation_forest"]


# ---------------------------------------------------------------- price creep
def items(prices, vendor=1, name="Cooking Oil 1L"):
    return [
        ItemRow(i + 1, vendor, name, D0 + timedelta(days=30 * i), p) for i, p in enumerate(prices)
    ]


def test_price_creep_flags_latest_invoice_when_unit_price_rises():
    flags = price_creep(items([520, 525, 530, 660]))
    assert len(flags) == 1 and flags[0].document_id == 4
    assert flags[0].evidence["increase_pct"] == pytest.approx(25.7, abs=0.2)
    assert flags[0].severity == "medium"
    assert price_creep(items([520, 525, 530, 800]))[0].severity == "high"  # > 30%


def test_price_creep_ignores_stable_prices_thin_history_and_other_vendors():
    assert price_creep(items([520, 525, 530, 540])) == []
    assert price_creep(items([520, 900])) == []  # only two observations
    mixed = items([520, 525], vendor=1) + items([900], vendor=2)
    assert price_creep(mixed) == []
    assert item_key("Cooking Oil, 1L!") == item_key("cooking  oil 1l")
