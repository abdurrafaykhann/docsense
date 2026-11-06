"""Field-level extraction metrics.

Truth semantics per field: key missing = not annotated (ignored); key present with None =
annotated as absent (a non-null prediction is then a false positive).
"""

from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz

SCALAR_FIELDS = [
    "vendor_name",
    "ntn",
    "strn",
    "invoice_number",
    "invoice_date",
    "subtotal",
    "tax_rate",
    "sales_tax",
    "total",
]
NUMERIC = {"subtotal", "tax_rate", "sales_tax", "total"}
DIGITS = {"ntn", "strn"}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s))


def field_match(name: str, pred, truth) -> bool:
    if pred in (None, "") or truth in (None, ""):
        return False
    if name in NUMERIC:
        try:
            return abs(float(pred) - float(truth)) <= 0.011
        except (TypeError, ValueError):
            return False
    if name in DIGITS:
        return _digits(pred) == _digits(truth) != ""
    if name == "invoice_date":
        return str(pred).strip() == str(truth).strip()
    if name == "invoice_number":
        return _norm(pred) == _norm(truth)
    return _norm(pred) == _norm(truth) or fuzz.ratio(_norm(pred), _norm(truth)) >= 90


def _present(v) -> bool:
    return v not in (None, "")


def _similar(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return fuzz.ratio(na, nb) >= 70 or fuzz.partial_ratio(na, nb) >= 90


def match_items(pred: list[dict], truth: list[dict]) -> tuple[int, int, int]:
    """Greedy one-to-one match of line items: same amount and similar description.

    Returns (true_positives, n_pred, n_truth).
    """
    used: set[int] = set()
    tp = 0
    for t in truth:
        for i, p in enumerate(pred):
            if i in used:
                continue
            pa, ta = p.get("amount"), t.get("amount")
            if pa is None or ta is None or abs(float(pa) - float(ta)) > 0.011:
                continue
            pd, td = p.get("description"), t.get("description")
            if not td or (pd and _similar(pd, td)):
                used.add(i)
                tp += 1
                break
    return tp, len(pred), len(truth)


def prf(tp: int, n_pred: int, n_truth: int) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_truth if n_truth else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "support": n_truth}


def score_document(pred: dict, truth: dict) -> dict:
    """Per-document outcome used by `aggregate`."""
    fields = {}
    annotated_ok = []
    for name in SCALAR_FIELDS:
        if name not in truth:
            continue
        t, p = truth[name], pred.get(name)
        ok = field_match(name, p, t) if _present(t) else (not _present(p))
        fields[name] = {
            "tp": int(_present(t) and ok),
            "pred": int(_present(p)),
            "truth": int(_present(t)),
        }
        annotated_ok.append(ok)
    items = None
    if "line_items" in truth:
        items = match_items(pred.get("line_items") or [], truth["line_items"] or [])
    return {
        "fields": fields,
        "items": items,
        "all_correct": bool(annotated_ok) and all(annotated_ok),
        "total_exact": field_match("total", pred.get("total"), truth["total"])
        if _present(truth.get("total"))
        else None,
    }


def aggregate(docs: list[dict]) -> dict:
    """docs: [{score: score_document(..), needs_review: bool, issues: [..]}]"""
    agg = defaultdict(lambda: [0, 0, 0])
    items = [0, 0, 0]
    totals = []
    for d in docs:
        for name, c in d["score"]["fields"].items():
            agg[name][0] += c["tp"]
            agg[name][1] += c["pred"]
            agg[name][2] += c["truth"]
        if d["score"]["items"]:
            for k in range(3):
                items[k] += d["score"]["items"][k]
        if d["score"]["total_exact"] is not None:
            totals.append(d["score"]["total_exact"])
    per_field = {n: prf(*agg[n]) for n in SCALAR_FIELDS if n in agg}
    micro = prf(
        sum(v[0] for v in agg.values()),
        sum(v[1] for v in agg.values()),
        sum(v[2] for v in agg.values()),
    )
    n = len(docs) or 1
    wrong = [d for d in docs if not d["score"]["all_correct"]]
    accepted = [d for d in docs if not d["needs_review"]]
    return {
        "n_docs": len(docs),
        "per_field": per_field,
        "micro": micro,
        "line_items": prf(*items) if items[2] else None,
        "total_exact_match": round(sum(totals) / len(totals), 4) if totals else None,
        "review_rate": round(sum(d["needs_review"] for d in docs) / n, 4),
        # of documents with any wrong field, how many did we route to a human?
        "error_catch_rate": round(sum(d["needs_review"] for d in wrong) / len(wrong), 4)
        if wrong
        else None,
        # of documents auto-accepted, how many were fully correct?
        "auto_accept_precision": round(
            sum(d["score"]["all_correct"] for d in accepted) / len(accepted), 4
        )
        if accepted
        else None,
        "validation_pass_rate": round(sum(not d["issues"] for d in docs) / n, 4),
    }
