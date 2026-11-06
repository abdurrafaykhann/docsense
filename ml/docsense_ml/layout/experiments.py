"""Experiments a-d (synthetic -> real gap), tracked with MLflow, results into docs/eval-results.

a  synthetic, no augmentation
b  synthetic, basic augmentation (geometry + blur + jpeg)
c  synthetic, full augmentation (texture, shadows, creases, stains, low light, desk, crops)
d  c + 30 real CORD receipts (human table/totals boxes + pseudo-labels for the other classes)

python -m docsense_ml.layout.experiments --epochs 12 --exps a,b,c,d
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ..synth.build import write_data_yaml
from ..synth.render import CLASSES
from . import yolo

EXPERIMENTS = {
    "a": ("none", "synthetic, no augmentation"),
    "b": ("basic", "synthetic, basic augmentation"),
    "c": ("full", "synthetic, full augmentation"),
    "d": ("full", "full augmentation + 30 real receipts (few-shot mix)"),
    "e": ("scene", "full augmentation + scene placement (page small on a table/hand)"),
    "f": ("scene", "scene augmentation + 30 real receipts (few-shot mix)"),
}
MIX_COPIES = 3  # oversample the few real images so they matter next to hundreds of synthetic ones
PSEUDO_CONF = 0.5


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def pseudo_label_mix(weights: Path, real: Path, out: Path, imgsz: int) -> int:
    """Real 'tune' images: human CORD boxes (table, totals) + confident model boxes (the rest)."""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    img_dir, lab_dir = out / "images" / "train", out / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lab_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for img in sorted((real / "images" / "tune").glob("*.png")):
        human = (real / "labels" / "tune" / f"{img.stem}.txt").read_text().splitlines()
        res = model.predict(str(img), imgsz=imgsz, conf=PSEUDO_CONF, device="cpu", verbose=False)[0]
        pseudo = []
        for cls, (cx, cy, w, h) in zip(
            res.boxes.cls.tolist(), res.boxes.xywhn.tolist(), strict=True
        ):
            if CLASSES[int(cls)] in ("vendor", "meta", "other"):
                pseudo.append(f"{int(cls)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        for k in range(MIX_COPIES):
            shutil.copy(img, img_dir / f"{img.stem}_{k}.png")
            (lab_dir / f"{img.stem}_{k}.txt").write_text(
                "\n".join(human + pseudo), encoding="utf-8"
            )
        n += 1
    return n


def build_mixed_dataset(
    synth_full: Path, real: Path, weights: Path, out: Path, imgsz: int, val_dir: Path | None = None
) -> Path:
    mix = out / "real_mix"
    if mix.exists():
        shutil.rmtree(mix)
    n = pseudo_label_mix(weights, real, mix, imgsz)
    print(f"mixed {n} real receipts x{MIX_COPIES}")
    yaml = out / "mixed.yaml"
    yaml.write_text(
        f"path: {out.resolve().as_posix()}\n"
        f"train:\n  - {(synth_full / 'images' / 'train').resolve().as_posix()}\n"
        f"  - {(mix / 'images' / 'train').resolve().as_posix()}\n"
        f"val: {(synth_full / 'images' / 'val').resolve().as_posix()}\n"
        "names:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)),
        encoding="utf-8",
    )
    return yaml


def log_mlflow(name: str, desc: str, params: dict, run_dir: Path, results: dict, tracking: str):
    import mlflow

    mlflow.set_tracking_uri(tracking)
    mlflow.set_experiment("docsense-layout")
    with mlflow.start_run(run_name=f"exp-{name}"):
        mlflow.set_tags({"description": desc, "git_sha": git_sha()})
        mlflow.log_params(params)
        for step, row in enumerate(yolo.read_results(run_dir)):
            for k, v in row.items():
                if k != "epoch":
                    mlflow.log_metric(
                        k.replace("(", "_").replace(")", "").replace("/", "."), v, step=step
                    )
        for ds, r in results.items():
            mlflow.log_metric(f"{ds}.map50", r["map50"])
            for c, ap in r["per_class_ap50"].items():
                if ap is not None:
                    mlflow.log_metric(f"{ds}.ap50.{c}", ap)
        for f in ("results.png", "confusion_matrix_normalized.png"):
            if (run_dir / f).exists():
                mlflow.log_artifact(str(run_dir / f))
        best = run_dir / "weights" / "best.pt"
        if best.exists():
            mlflow.log_artifact(str(best), artifact_path="weights")


def write_result(
    out_dir: Path, exp: str, desc: str, dataset: str, n: int, metrics: dict, params: dict
):
    payload = {
        "kind": "layout",
        "dataset": dataset,
        "arm": f"exp-{exp}: {desc}",
        "n": n,
        "git_sha": git_sha(),
        "created_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "config": params,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"layout-{exp}-{dataset}.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8"
    )


def count_images(directory: Path) -> int:
    return sum(1 for _ in directory.glob("*.*"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", default="ml/data/synth")
    ap.add_argument("--real", default="ml/data/cord_layout")
    ap.add_argument("--exps", default="a,b,c,d")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--imgsz", type=int, default=480)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--base", default="yolo11n.pt")
    ap.add_argument("--runs", default="ml/runs")
    ap.add_argument("--reuse", action="store_true", help="skip training if finished weights exist")
    ap.add_argument("--results", default="docs/eval-results")
    ap.add_argument("--tracking", default="sqlite:///ml/runs/mlflow.db")
    a = ap.parse_args()

    synth, real, runs = Path(a.synth), Path(a.real), Path(a.runs)
    runs.mkdir(parents=True, exist_ok=True)
    n_syn = count_images(synth / "valfull" / "images" / "val")
    n_real = count_images(real / "images" / "test")
    trained: dict[str, Path] = {}

    for exp in a.exps.split(","):
        level, desc = EXPERIMENTS[exp]
        data = synth / level / "data.yaml"
        if exp in ("d", "f"):
            donor = "c" if exp == "d" else "e"  # pseudo-labels come from the matching no-real model
            base_w = trained.get(donor) or runs / "yolo" / f"exp-{donor}" / "weights" / "best.pt"
            data = build_mixed_dataset(
                synth / level,
                real,
                base_w,
                runs / f"mixed-{exp}",
                a.imgsz,
                val_dir=synth / "valfull" / "images" / "val",
            )
        params = {"exp": exp, "aug": level, "epochs": a.epochs, "imgsz": a.imgsz, "batch": a.batch,
                  "base": a.base, "real_mix": exp in ("d", "f")}  # fmt: skip
        print(f"=== experiment {exp}: {desc}")
        existing = runs / "yolo" / f"exp-{exp}" / "weights" / "best.pt"
        rows = runs / "yolo" / f"exp-{exp}" / "results.csv"
        done = rows.exists() and len(rows.read_text().splitlines()) > a.epochs
        if a.reuse and done and existing.exists():
            best = existing
        else:
            best = yolo.train(
                data,
                f"exp-{exp}",
                epochs=a.epochs,
                imgsz=a.imgsz,
                batch=a.batch,
                base=a.base,
                project=runs / "yolo",
            )
        trained[exp] = best
        results = {
            "synthetic-hard": yolo.evaluate(best, synth / "valfull" / "data.yaml", imgsz=a.imgsz),
            "cord-real-test": yolo.evaluate(best, real / "data.yaml", imgsz=a.imgsz),
        }
        log_mlflow(exp, desc, params, runs / "yolo" / f"exp-{exp}", results, a.tracking)
        write_result(
            Path(a.results), exp, desc, "synthetic-hard", n_syn, results["synthetic-hard"], params
        )
        write_result(
            Path(a.results), exp, desc, "cord-real-test", n_real, results["cord-real-test"], params
        )
        print(
            json.dumps(
                {k: {"map50": v["map50"], **v["per_class_ap50"]} for k, v in results.items()}
            )
        )


if __name__ == "__main__":
    main()


__all__ = ["write_data_yaml"]
