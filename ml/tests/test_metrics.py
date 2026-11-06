import docsense_ml  # noqa: F401  (adds backend/ to sys.path)
from docsense_ml.metrics import aggregate, field_match, match_items, prf, score_document


def test_field_match_rules():
    assert field_match("total", 3540.0, 3540)
    assert field_match("total", 3540.004, 3540)
    assert not field_match("total", 3541, 3540)
    assert field_match("ntn", "1234567-8", "12345678")
    assert field_match("vendor_name", "Acme Traders.", "ACME TRADERS")
    assert field_match("vendor_name", "Acme Tradrs", "Acme Traders")  # fuzzy >= 90
    assert not field_match("vendor_name", "Other Shop", "Acme Traders")
    assert not field_match("invoice_date", "2024-03-12", "2024-12-03")
    assert not field_match("total", None, 5)


def test_prf_hand_computed():
    assert prf(8, 10, 16) == {"precision": 0.8, "recall": 0.5, "f1": 0.6154, "support": 16}
    assert prf(0, 0, 0)["f1"] == 0.0


def test_match_items_one_to_one_and_description_check():
    truth = [
        {"description": "Nasi Goreng", "amount": 25000},
        {"description": "Es Teh", "amount": 5000},
        {"description": "Es Teh", "amount": 5000},
    ]
    pred = [
        {"description": "nasi goreng", "amount": 25000},
        {"description": "Es Teh", "amount": 5000},
        {"description": "Completely different", "amount": 5000},  # amount ok, text wrong
    ]
    assert match_items(pred, truth) == (2, 3, 3)


def test_unannotated_fields_are_ignored_but_annotated_absent_penalises_fp():
    truth = {"total": 100, "subtotal": None}  # vendor not annotated at all
    pred = {"total": 100, "subtotal": 90, "vendor_name": "Whatever"}
    s = score_document(pred, truth)
    assert set(s["fields"]) == {"total", "subtotal"}
    assert s["fields"]["subtotal"] == {"tp": 0, "pred": 1, "truth": 0}
    assert s["all_correct"] is False


def test_aggregate_and_routing_metrics():
    def doc(pred_total, review, issues=()):
        return {
            "score": score_document({"total": pred_total}, {"total": 100}),
            "needs_review": review,
            "issues": list(issues),
        }

    docs = [
        doc(100, False),  # correct, auto-accepted
        doc(100, True),  # correct, sent to review (wasted effort)
        doc(90, True, ["total_mismatch"]),  # wrong, caught
        doc(80, False),  # wrong, slipped through
    ]
    a = aggregate(docs)
    assert a["total_exact_match"] == 0.5
    assert a["per_field"]["total"]["precision"] == 0.5 and a["per_field"]["total"]["recall"] == 0.5
    assert a["review_rate"] == 0.5
    assert a["error_catch_rate"] == 0.5  # 1 of 2 wrong docs flagged
    assert a["auto_accept_precision"] == 0.5  # 1 of 2 accepted docs correct
    assert a["validation_pass_rate"] == 0.75
