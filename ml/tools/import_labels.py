"""Turn labeler.html's labels.json into a YOLO dataset (images + labels + data.yaml).

python ml/tools/import_labels.py labels.json my_receipts/ ml/data/own_layout --test-frac 0.7
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docsense_ml.synth.build import write_data_yaml  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("images")
    ap.add_argument("out")
    ap.add_argument("--test-frac", type=float, default=0.6, help="held-out share (real test set)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    labels = {k: v for k, v in json.loads(Path(a.labels).read_text()).items() if v}
    names = sorted(labels)
    random.Random(a.seed).shuffle(names)
    n_test = max(1, round(len(names) * a.test_frac))
    out = Path(a.out)
    for i, name in enumerate(names):
        split = "test" if i < n_test else "tune"
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(a.images) / name, out / "images" / split / name)
        lines = [f"{int(c)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for c, cx, cy, w, h in labels[name]]
        (out / "labels" / split / f"{Path(name).stem}.txt").write_text("\n".join(lines))
    write_data_yaml(out, train="images/tune", val="images/test")
    print(f"{len(names)} labelled images -> {out} ({n_test} test / {len(names) - n_test} tune)")


if __name__ == "__main__":
    main()
