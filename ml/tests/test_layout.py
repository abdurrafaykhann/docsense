import json

import pytest

from docsense_ml.layout import experiments, real, yolo
from docsense_ml.synth.build import write_data_yaml
from docsense_ml.synth.render import CLASSES


def quad(x0, y0, x1, y1):
    return {"x1": x0, "y1": y0, "x2": x1, "y2": y0, "x3": x1, "y3": y1, "x4": x0, "y4": y1}


def test_quads_to_box_unions_pads_and_normalises():
    box = real.quads_to_box([quad(100, 200, 200, 220), quad(120, 300, 300, 340)], 400, 800)
    cx, cy, w, h = box
    assert w == pytest.approx((300 - 100) / 400 + 2 * real.PAD)
    assert h == pytest.approx((340 - 200) / 800 + 2 * real.PAD)
    assert cx == pytest.approx((100 + 300) / 2 / 400)
    assert cy == pytest.approx((200 + 340) / 2 / 800)
    assert real.quads_to_box([], 400, 800) is None


def test_quads_to_box_clamps_to_image_and_drops_degenerate_boxes():
    cx, cy, w, h = real.quads_to_box([quad(-20, -10, 500, 900)], 400, 800)
    assert (cx, cy, w, h) == pytest.approx((0.5, 0.5, 1.0, 1.0))
    assert real.quads_to_box([quad(10, 10, 11, 11)], 1000, 1000) is None


def test_cord_categories_map_to_table_and_totals_only():
    lines = [
        {"category": "menu.nm", "words": [{"quad": quad(10, 100, 200, 120)}]},
        {"category": "menu.price", "words": [{"quad": quad(250, 100, 380, 120)}]},
        {"category": "menu.num", "words": [{"quad": quad(10, 140, 200, 160)}]},
        {"category": "sub_total.tax_price", "words": [{"quad": quad(250, 300, 380, 320)}]},
        {"category": "total.total_price", "words": [{"quad": quad(250, 340, 380, 360)}]},
        {"category": "void_menu.nm", "words": [{"quad": quad(0, 0, 5, 5)}]},
    ]
    boxes = dict(real.cord_layout_boxes(lines, 400, 500))
    assert set(boxes) == {real.TABLE, real.TOTALS}
    # table spans the three menu lines (y 100..160) and totals the tax + total lines (y 300..360)
    assert boxes[real.TABLE][1] < boxes[real.TOTALS][1]
    assert boxes[real.TABLE][3] == pytest.approx(60 / 500 + 2 * real.PAD)
    assert boxes[real.TOTALS][3] == pytest.approx(60 / 500 + 2 * real.PAD)


def test_data_yaml_has_five_classes_in_plan_order(tmp_path):
    write_data_yaml(tmp_path)
    text = (tmp_path / "data.yaml").read_text()
    for i, c in enumerate(CLASSES):
        assert f"  {i}: {c}" in text


def test_read_results_parses_ultralytics_csv(tmp_path):
    (tmp_path / "results.csv").write_text(
        "                  epoch,      train/box_loss,   metrics/mAP50(B)\n"
        "                      1,             1.5,              0.2\n"
        "                      2,             1.1,              0.55\n"
    )
    rows = yolo.read_results(tmp_path)
    assert [r["epoch"] for r in rows] == [1.0, 2.0]
    assert rows[1]["metrics/mAP50(B)"] == 0.55


def test_builtin_augmentation_is_disabled_and_never_flips():
    assert yolo.NO_BUILTIN_AUG["fliplr"] == 0 and yolo.NO_BUILTIN_AUG["mosaic"] == 0
    assert all(v == 0 for v in yolo.NO_BUILTIN_AUG.values())


def test_experiments_table_and_result_files(tmp_path):
    assert {k: v[0] for k, v in experiments.EXPERIMENTS.items()} == {
        "a": "none",
        "b": "basic",
        "c": "full",
        "d": "full",
    }
    metrics = {"map50": 0.5, "map50_95": 0.3, "per_class_ap50": {"table": 0.7, "totals": 0.3}}
    experiments.write_result(tmp_path, "c", "desc", "cord-real-test", 65, metrics, {"epochs": 1})
    payload = json.loads((tmp_path / "layout-c-cord-real-test.json").read_text())
    assert payload["kind"] == "layout" and payload["n"] == 65
    assert payload["metrics"]["per_class_ap50"]["table"] == 0.7
