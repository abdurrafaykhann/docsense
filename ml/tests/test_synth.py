import re
from datetime import date

import numpy as np
import pytest
from apps.validation.rules import is_valid_ntn, is_valid_strn, validate
from apps.validation.schema import InvoiceExtraction

from docsense_ml.synth.augment import augment
from docsense_ml.synth.generator import TEMPLATES, make_invoice
from docsense_ml.synth.render import CLASSES, render_html, to_yolo_lines

SEEDS = range(60)


def test_generated_ntn_strn_pass_the_validators():
    for s in SEEDS:
        inv = make_invoice(s)
        assert is_valid_ntn(inv.ntn), inv.ntn
        assert is_valid_strn(inv.strn), inv.strn


def test_generated_invoices_are_arithmetically_consistent():
    """Clean synthetic data must pass every validation rule (so rules flag only real errors)."""
    for s in SEEDS:
        inv = make_invoice(s, today=date(2025, 6, 30))
        issues = validate(InvoiceExtraction.model_validate(inv.truth()), today=date(2025, 7, 1))
        assert issues == [], (s, issues)
        assert inv.total == pytest.approx(inv.subtotal + inv.sales_tax, abs=0.01)


def test_generation_is_deterministic_and_seed_sensitive():
    assert make_invoice(5).truth() == make_invoice(5).truth()
    assert make_invoice(5).truth() != make_invoice(6).truth()


def test_all_templates_and_categories_are_reachable():
    seen_t = {make_invoice(s).template for s in range(300)}
    assert seen_t == set(TEMPLATES)
    assert len({make_invoice(s).category for s in range(80)}) == 6


@pytest.mark.parametrize("tpl", TEMPLATES)
def test_template_html_has_all_region_and_field_markers(tpl):
    inv = make_invoice(11, tpl)
    html = render_html(inv)
    for cls in CLASSES:
        assert f'data-region="{cls}"' in html, (tpl, cls)
    for field in ("vendor_name", "ntn", "strn", "invoice_number", "invoice_date", "subtotal",
                  "sales_tax", "total"):  # fmt: skip
        assert f'data-field="{field}"' in html, (tpl, field)
    # printed values come from the truth
    assert inv.vendor_name.replace("&", "&amp;").lower() in html.lower()
    assert f"{inv.total:,.2f}" in html


def test_yolo_lines_geometry_and_degenerate_boxes_dropped():
    regions = [
        {"cls": "vendor", "bbox": [0.1, 0.1, 0.5, 0.2]},
        {"cls": "totals", "bbox": [0.5, 0.8, 0.9, 0.9]},
        {"cls": "other", "bbox": [0.1, 0.5, 0.1001, 0.5001]},  # degenerate
    ]
    lines = to_yolo_lines(regions)
    assert len(lines) == 2
    cls, cx, cy, w, h = lines[0].split()
    assert (int(cls), float(cx), float(cy)) == (0, pytest.approx(0.3), pytest.approx(0.15))
    assert (float(w), float(h)) == (pytest.approx(0.4), pytest.approx(0.1))


def fake_page():
    img = np.full((600, 450, 3), 245, np.uint8)
    img[50:120, 40:400] = 30  # "vendor" slab
    img[300:420, 40:400] = 90
    boxes = [[0.5, 0.14, 0.8, 0.12], [0.5, 0.6, 0.8, 0.2]]
    return img, boxes, [0, 2]


@pytest.mark.parametrize("level", ["basic", "full"])
def test_augmentation_keeps_valid_boxes_and_changes_pixels(level):
    img, boxes, labels = fake_page()
    for seed in range(12):
        out, bx, lb = augment(img, boxes, labels, level, seed=seed)
        assert out.dtype == np.uint8 and out.ndim == 3 and out.shape[2] == 3
        assert len(bx) == len(lb) <= 2
        for cx, cy, w, h in bx:
            assert 0 <= cx - w / 2 + 1e-6 and cx + w / 2 <= 1 + 1e-6, (level, seed, bx)
            assert 0 <= cy - h / 2 + 1e-6 and cy + h / 2 <= 1 + 1e-6, (level, seed, bx)
            assert w > 0 and h > 0
        assert not (out.shape == img.shape and np.array_equal(out, img))


def test_augmentation_is_deterministic_per_seed_and_none_is_identity():
    img, boxes, labels = fake_page()
    a = augment(img, boxes, labels, "full", seed=3)
    b = augment(img, boxes, labels, "full", seed=3)
    c = augment(img, boxes, labels, "full", seed=4)
    assert np.array_equal(a[0], b[0]) and a[1] == b[1]
    assert a[0].shape != c[0].shape or not np.array_equal(a[0], c[0])
    out, bx, lb = augment(img, boxes, labels, "none", seed=3)
    assert out is img and bx == boxes and lb == labels


def test_data_yaml_class_order_matches_plan():
    assert CLASSES == ["vendor", "meta", "table", "totals", "other"]
    assert re.fullmatch(r"[a-z]+", CLASSES[0])
