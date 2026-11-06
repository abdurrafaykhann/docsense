import numpy as np
from apps.llm.cache import MemoryCache
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline.ocr import FakeOCR
from apps.validation.grounding import words_from_lines
from PIL import Image

import docsense_ml  # noqa: F401
from docsense_ml.baselines import RegexModel, extract_text, parse_amount
from docsense_ml.caches import CachedOCR, FileCache, Paced
from docsense_ml.cord import cord_truth, parse_money
from docsense_ml.evalset import load_set, write_manifest
from docsense_ml.evaluate import evaluate

TEXT = """ACME TRADERS
NTN 1234567-8 STRN 1234567890123
Invoice No INV-0042
Date 12/03/2024
Widget 2 500.00 1000.00
Gadget 1 2000.00 2000.00
Subtotal 3,000.00
Sales Tax 18% 540.00
Total 3,540.00"""


def test_regex_baseline_extracts_the_basics():
    r = extract_text(TEXT)
    assert r["vendor_name"] == "ACME TRADERS"
    assert r["invoice_date"] == "2024-03-12"
    assert r["ntn"] == "1234567-8" and r["strn"] == "1234567890123"
    assert r["invoice_number"] == "INV-0042"
    assert (r["subtotal"], r["sales_tax"], r["total"], r["tax_rate"]) == (3000, 540, 3540, 18)
    assert [i["amount"] for i in r["line_items"]] == [1000, 2000]


def test_amount_parsing_locales():
    assert parse_amount("3,540.00") == 3540
    assert parse_amount("1.346.000", idr=True) == 1346000
    assert parse_amount("75.000", idr=True) == 75000
    assert parse_amount("12,5") == 12.5
    assert parse_money("1,346,000") == 1346000 and parse_money("45.000") == 45000


def test_cord_truth_mapping_handles_dict_menu_and_missing_fields():
    gt = {
        "menu": {"nm": "NASI", "cnt": "2", "price": "50.000"},
        "sub_total": {"subtotal_price": "50.000", "tax_price": "5.000"},
        "total": {"total_price": "55.000"},
    }
    t = cord_truth(gt)
    assert t["total"] == 55000 and t["sales_tax"] == 5000 and t["subtotal"] == 50000
    assert t["line_items"] == [{"description": "NASI", "quantity": 2, "amount": 50000}]
    assert "sales_tax" not in cord_truth({"total": {"total_price": "9"}, "menu": []})


def test_evalset_roundtrip(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (50, 50), "white").save(tmp_path / "images" / "a.png")
    write_manifest(tmp_path, [{"id": "a", "image": "images/a.png", "truth": {"total": 5}}])
    s = load_set(tmp_path)[0]
    assert s.id == "a" and s.truth == {"total": 5} and s.load_image().shape == (50, 50, 3)


def make_set(tmp_path, n=3):
    (tmp_path / "images").mkdir()
    rows = []
    for i in range(n):
        Image.new("RGB", (80, 100), "white").save(tmp_path / "images" / f"{i}.png")
        total = 3540 if i < 2 else 3000  # third doc: OCR says 3,540 but truth is 3000
        rows.append(
            {
                "id": f"d{i}",
                "image": f"images/{i}.png",
                "truth": {"vendor_name": "ACME TRADERS", "total": total},
                "words": [w.as_dict() for w in words_from_lines(TEXT.splitlines())],
            }
        )
    write_manifest(tmp_path, rows)
    return load_set(tmp_path)


def test_evaluate_end_to_end_with_oracle_ocr_and_regex_arm(tmp_path):
    samples = make_set(tmp_path)
    llm = LLMClient([Provider("regex", RegexModel())], cache=MemoryCache())
    out = evaluate(samples, ocr=FakeOCR(), llm=llm, oracle_ocr=True)
    m = out["metrics"]
    assert m["n_docs"] == 3 and m["errors"] == 0
    assert m["total_exact_match"] == round(2 / 3, 4)
    assert m["per_field"]["vendor_name"]["f1"] == 1.0
    assert m["llm_requests"] == 1  # identical prompts -> cache hits for the other two
    assert m["mean_prompt_tokens_est"] > 0
    # the wrong doc passes all validators (arithmetic is consistent), so it is NOT caught:
    assert m["error_catch_rate"] == 0.0 and m["review_rate"] == 0.0


def test_evaluate_isolates_a_failing_sample(tmp_path):
    samples = make_set(tmp_path, 2)
    llm = LLMClient([Provider("f", FakeChatModel([ValueError("boom"), {"total": 3540}]))])
    out = evaluate(samples, ocr=FakeOCR(["Total 3,540.00"]), llm=llm)
    assert out["metrics"]["errors"] >= 1 and out["docs"][0]["needs_review"] is True


def test_caches_and_pacing(tmp_path):
    ocr = CachedOCR(FakeOCR(["a b"]), tmp_path)
    img = np.zeros((10, 10, 3), np.uint8)
    ocr.read(img)
    ocr.read(img)
    assert (ocr.hits, ocr.misses) == (1, 1)
    fc = FileCache(tmp_path)
    fc.set("k", {"x": 1})
    assert fc.get("k") == {"x": 1} and fc.get("nope") is None

    naps, now = [], [0.0]
    paced = Paced(FakeChatModel(default={"total": 1}), 2.5, sleep=naps.append, clock=lambda: now[0])
    from apps.validation.schema import InvoiceExtraction

    r = paced.with_structured_output(InvoiceExtraction)
    r.invoke([])
    now[0] = 1.0
    r.invoke([])
    assert naps == [1.5]


DECOY = TEXT + "\nThank you! Total savings this year 99,999.00\nCall 0300-1234567"


def test_region_labels_stop_footer_decoys_from_hijacking_fields():
    whole = extract_text(DECOY)
    assert whole["total"] == 99999  # last 'total' line wins: wrong without regions
    sectioned = (
        "[VENDOR]\nACME TRADERS\nNTN 1234567-8 STRN 1234567890123\n"
        "[META]\nInvoice No INV-0042\nDate 12/03/2024\n"
        "[TABLE]\nWidget 2 500.00 1000.00\nGadget 1 2000.00 2000.00\n"
        "[TOTALS]\nSubtotal 3,000.00\nSales Tax 18% 540.00\nTotal 3,540.00\n"
        "[OTHER]\nThank you! Total savings this year 99,999.00\nCall 0300-1234567"
    )
    r = extract_text(sectioned)
    assert (r["total"], r["subtotal"], r["sales_tax"], r["tax_rate"]) == (3540, 3000, 540, 18)
    assert r["vendor_name"] == "ACME TRADERS" and r["invoice_date"] == "2024-03-12"
    assert [i["amount"] for i in r["line_items"]] == [1000, 2000]


def test_oracle_layout_arm_beats_whole_page_on_decoy_receipts(tmp_path):
    from apps.pipeline.layout import FakeLayout, Region

    lines = DECOY.splitlines()
    n = len(lines)

    def band(a, b):
        return [0.0, a / (n + 1), 1.0, (b + 1) / (n + 1)]

    regions = [
        {"cls": "vendor", "bbox": band(0, 1)},
        {"cls": "meta", "bbox": band(2, 3)},
        {"cls": "table", "bbox": band(4, 5)},
        {"cls": "totals", "bbox": band(6, 8)},
        {"cls": "other", "bbox": band(9, 10)},
    ]
    (tmp_path / "images").mkdir()
    Image.new("RGB", (80, 100), "white").save(tmp_path / "images" / "0.png")
    write_manifest(
        tmp_path,
        [
            {
                "id": "d0",
                "image": "images/0.png",
                "truth": {"total": 3540, "vendor_name": "ACME TRADERS"},
                "words": [w.as_dict() for w in words_from_lines(lines)],
                "meta": {"regions": regions},
            }
        ],
    )
    samples = load_set(tmp_path)

    def run(**kw):
        llm = LLMClient([Provider("regex", RegexModel())], cache=MemoryCache())
        return evaluate(samples, ocr=FakeOCR(), llm=llm, oracle_ocr=True, **kw)["metrics"]

    assert run()["total_exact_match"] == 0.0  # arm A: whole page, decoy wins
    assert run(oracle_layout=True)["total_exact_match"] == 1.0  # arm C: oracle regions
    layout = FakeLayout([Region(r["cls"], r["bbox"]) for r in regions])
    assert run(layout=layout)["total_exact_match"] == 1.0  # arm B: a layout detector
