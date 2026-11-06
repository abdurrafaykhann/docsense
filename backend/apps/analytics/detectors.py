"""Anomaly / fraud detectors. Pure Python + NumPy + scikit-learn: no Django, easy to test and
to compare in the notebook (ml/notebooks/02_anomaly_methods.ipynb).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import numpy as np


@dataclass
class InvoiceRow:
    document_id: int
    vendor_id: int | None
    number: str
    date: date | None
    total: float | None
    subtotal: float | None = None
    sales_tax: float | None = None
    n_items: int = 0
    sha256: str = ""
    phash: str = ""


@dataclass
class ItemRow:
    document_id: int
    vendor_id: int | None
    description: str
    date: date | None
    unit_price: float | None


@dataclass
class FlagSpec:
    document_id: int
    kind: str  # exact_dup | near_dup | image_dup | amount_outlier | price_creep
    severity: str  # high | medium | low
    evidence: dict = field(default_factory=dict)


# ------------------------------------------------------------------------ duplicates
def _norm_number(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def find_duplicates(
    rows: list[InvoiceRow], near_days: int = 3, phash_distance: int = 6
) -> list[FlagSpec]:
    """Flag the *later* document of each duplicate pair, pointing at the earlier one.

    exact: same file hash, or same vendor + same invoice number
    near : same vendor + same total + dates within `near_days`
    image: perceptual hashes within `phash_distance` bits (re-photographed / re-saved copy)
    Each document gets only its strongest duplicate flag.
    """
    rows = sorted(rows, key=lambda r: r.document_id)
    flags: dict[int, FlagSpec] = {}

    def add(later: InvoiceRow, earlier: InvoiceRow, kind: str, sev: str, **ev) -> None:
        cur = flags.get(later.document_id)
        order = {"exact_dup": 0, "near_dup": 1, "image_dup": 2}
        if cur is None or order[kind] < order[cur.kind]:
            flags[later.document_id] = FlagSpec(
                later.document_id, kind, sev, {"duplicate_of": earlier.document_id, **ev}
            )

    for i, b in enumerate(rows):
        for a in rows[:i]:
            if b.sha256 and a.sha256 == b.sha256:
                add(b, a, "exact_dup", "high", reason="identical file")
            elif (
                b.vendor_id is not None
                and a.vendor_id == b.vendor_id
                and _norm_number(b.number)
                and _norm_number(a.number) == _norm_number(b.number)
            ):
                add(b, a, "exact_dup", "high", reason="same vendor and invoice number")
            elif (
                b.vendor_id is not None
                and a.vendor_id == b.vendor_id
                and b.total is not None
                and a.total is not None
                and abs(a.total - b.total) < 0.01
                and a.date
                and b.date
                and abs((a.date - b.date).days) <= near_days
            ):
                add(b, a, "near_dup", "medium", reason="same vendor, amount and close dates")
            elif a.phash and b.phash and hamming(a.phash, b.phash) <= phash_distance:
                add(b, a, "image_dup", "low", reason="visually near-identical image",
                    distance=hamming(a.phash, b.phash))  # fmt: skip
    return list(flags.values())


# ------------------------------------------------------------------------ amount outliers
def modified_z_scores(values: np.ndarray) -> np.ndarray:
    """Robust z-score: 0.6745 * (x - median) / MAD (falls back to mean absolute deviation)."""
    med = np.median(values)
    mad = np.median(np.abs(values - med))
    if mad > 0:
        return 0.6745 * (values - med) / mad
    mean_ad = np.mean(np.abs(values - med))
    return (values - med) / (1.253314 * mean_ad) if mean_ad > 0 else np.zeros_like(values)


def robust_outliers(
    rows: list[InvoiceRow], z_threshold: float = 3.5, min_per_vendor: int = 5
) -> list[FlagSpec]:
    """Per-vendor robust z-score on totals (log scale so multiplicative jumps stand out)."""
    by_vendor: dict[int, list[InvoiceRow]] = defaultdict(list)
    for r in rows:
        if r.vendor_id is not None and r.total and r.total > 0:
            by_vendor[r.vendor_id].append(r)
    out = []
    for vendor_rows in by_vendor.values():
        if len(vendor_rows) < min_per_vendor:
            continue
        totals = np.array([r.total for r in vendor_rows], dtype=float)
        z = modified_z_scores(np.log(totals))
        med = float(np.median(totals))
        for r, zi in zip(vendor_rows, z, strict=True):
            if abs(zi) >= z_threshold:
                out.append(
                    FlagSpec(
                        r.document_id,
                        "amount_outlier",
                        "high" if abs(zi) >= 2 * z_threshold else "medium",
                        {
                            "method": "robust_z",
                            "z": round(float(zi), 2),
                            "vendor_median": round(med, 2),
                            "total": r.total,
                            "direction": "high" if zi > 0 else "low",
                        },
                    )
                )
    return out


def isolation_outliers(
    rows: list[InvoiceRow], contamination: float = 0.03, min_rows: int = 30, seed: int = 0
) -> list[FlagSpec]:
    """Workspace-level IsolationForest on vendor-relative size, tax ratio and item count.

    Complements the per-vendor z-score: it also catches odd combinations (e.g. a normal total
    with an abnormal tax ratio) and vendors with too little history for a z-score.
    """
    from sklearn.ensemble import IsolationForest

    usable = [r for r in rows if r.total and r.total > 0]
    if len(usable) < min_rows:
        return []
    by_vendor: dict[int | None, list[float]] = defaultdict(list)
    for r in usable:
        by_vendor[r.vendor_id].append(r.total)
    med = {v: float(np.median(t)) for v, t in by_vendor.items()}
    overall = float(np.median([r.total for r in usable]))

    def feats(r: InvoiceRow) -> list[float]:
        base = med[r.vendor_id] if len(by_vendor[r.vendor_id]) >= 3 else overall
        tax = (r.sales_tax / r.subtotal) if r.subtotal and r.sales_tax is not None else 0.18
        return [float(np.log(r.total / base)), tax, float(r.n_items)]

    X = np.array([feats(r) for r in usable])
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed).fit(X)
    pred, score = model.predict(X), model.score_samples(X)
    return [
        FlagSpec(
            r.document_id,
            "amount_outlier",
            "medium",
            {"method": "isolation_forest", "score": round(float(s), 3), "total": r.total},
        )
        for r, p, s in zip(usable, pred, score, strict=True)
        if p == -1
    ]


def merge_outliers(*groups: list[FlagSpec]) -> list[FlagSpec]:
    """One amount_outlier flag per document; keep every method that fired and the max severity."""
    rank = {"low": 0, "medium": 1, "high": 2}
    merged: dict[int, FlagSpec] = {}
    for spec in (s for g in groups for s in g):
        cur = merged.get(spec.document_id)
        if cur is None:
            spec.evidence = {**spec.evidence, "methods": [spec.evidence["method"]]}
            merged[spec.document_id] = spec
        else:
            cur.evidence["methods"].append(spec.evidence["method"])
            cur.evidence.update({k: v for k, v in spec.evidence.items() if k not in cur.evidence})
            if rank[spec.severity] > rank[cur.severity]:
                cur.severity = spec.severity
    return list(merged.values())


# ------------------------------------------------------------------------ price creep
def item_key(description: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", description.lower()).split())


def price_creep(
    items: list[ItemRow], min_obs: int = 3, min_increase: float = 0.10
) -> list[FlagSpec]:
    """Same vendor + same item: latest unit price >= `min_increase` above the earlier median."""
    series: dict[tuple, list[ItemRow]] = defaultdict(list)
    for it in items:
        if it.vendor_id is not None and it.unit_price and it.date and it.description:
            series[(it.vendor_id, item_key(it.description))].append(it)
    out = []
    for (_, key), obs in series.items():
        obs.sort(key=lambda o: (o.date, o.document_id))
        if len(obs) < min_obs:
            continue
        prev = [o.unit_price for o in obs[:-1]]
        base = float(np.median(prev))
        last = obs[-1]
        change = last.unit_price / base - 1
        if change >= min_increase:
            out.append(
                FlagSpec(
                    last.document_id,
                    "price_creep",
                    "high" if change >= 0.3 else "medium",
                    {
                        "item": key,
                        "previous_median": round(base, 2),
                        "latest": last.unit_price,
                        "increase_pct": round(change * 100, 1),
                        "observations": len(obs),
                    },
                )
            )
    return out
