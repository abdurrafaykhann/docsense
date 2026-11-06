"""Active learning: turn approvals into training data, export it, retrain, compare, activate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.documents.models import Document, Region
from apps.pipeline.layout import CLASSES

from .models import ModelVersion, RetrainJob, TrainingSample

# A retrained model may be activated only if it does not get meaningfully worse anywhere.
MAX_DROP = 0.02


# --------------------------------------------------------------------------- capture
@transaction.atomic
def capture_sample(document: Document, truth: dict, field_boxes: dict, corrected: bool):
    """Called on approval. Stores page-1 image + final regions + corrected truth (idempotent)."""
    page = document.pages.first()
    if page is None:
        return None
    regions = [{"cls": r.cls, "bbox": r.bbox} for r in Region.objects.filter(page=page)]
    sample, _ = TrainingSample.objects.update_or_create(
        document=document,
        defaults={
            "workspace": document.workspace,
            "regions": regions,
            "truth": truth,
            "field_boxes": field_boxes,
            "corrected": corrected,
        },
    )
    with page.image.open("rb") as fh:
        sample.image.save(f"doc{document.id}.jpg", ContentFile(fh.read()), save=True)
    return sample


# --------------------------------------------------------------------------- export
def yolo_lines(regions: list[dict]) -> list[str]:
    lines = []
    for r in regions:
        if r["cls"] not in CLASSES:
            continue
        x0, y0, x1, y1 = r["bbox"]
        w, h = x1 - x0, y1 - y0
        if w > 0.005 and h > 0.002:
            lines.append(
                f"{CLASSES.index(r['cls'])} {x0 + w / 2:.6f} {y0 + h / 2:.6f} {w:.6f} {h:.6f}"
            )
    return lines


def export_feedback(out: Path, workspace_id: int | None = None) -> int:
    """Write a YOLO dataset (images/train + labels/train + manifest.jsonl) from approved samples."""
    out = Path(out)
    (out / "images" / "train").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "train").mkdir(parents=True, exist_ok=True)
    qs = TrainingSample.objects.exclude(regions=[])
    if workspace_id:
        qs = qs.filter(workspace_id=workspace_id)
    n = 0
    with (out / "manifest.jsonl").open("w", encoding="utf-8") as manifest:
        for s in qs.order_by("id"):
            name = f"fb{s.id:06d}"
            lines = yolo_lines(s.regions)
            if not lines:
                continue
            with s.image.open("rb") as fh:
                (out / "images" / "train" / f"{name}.jpg").write_bytes(fh.read())
            (out / "labels" / "train" / f"{name}.txt").write_text(
                "\n".join(lines), encoding="utf-8"
            )
            manifest.write(
                json.dumps(
                    {
                        "id": name,
                        "image": f"images/train/{name}.jpg",
                        "truth": s.truth,
                        "meta": {"corrected": s.corrected, "fields": s.field_boxes},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n += 1
    return n


# --------------------------------------------------------------------------- retrain
Runner = Callable[[dict], dict]


def ml_root() -> Path:
    return Path(settings.BASE_DIR).parent / "ml"


def current_weights() -> str | None:
    active = ModelVersion.objects.filter(is_active=True).first()
    if active and Path(active.path).exists():
        return active.path
    path = settings.LAYOUT_MODEL_PATH
    return path if path and Path(path).exists() else None


def subprocess_runner(args: dict) -> dict:
    """Run docsense_ml.layout.retrain in a child process (keeps torch out of Django)."""
    root = ml_root()
    cmd = [
        sys.executable, "-m", "docsense_ml.layout.retrain",
        "--feedback", args["feedback"], "--base", args["base"], "--out", args["out"],
        "--epochs", str(args["epochs"]), "--imgsz", str(args.get("imgsz", 416)),
        "--synth", str(root / "data" / "synth"), "--real", str(root / "data" / "cord_layout"),
    ]  # fmt: skip
    env = {**os.environ, "PYTHONPATH": str(root)}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=root.parent)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:] or proc.stdout[-1500:])
    last = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    if not last:
        raise RuntimeError("retrain produced no RESULT line:\n" + proc.stdout[-800:])
    return json.loads(last[-1][len("RESULT ") :])


def compare(previous: dict, new: dict) -> dict:
    """Per eval-set mAP@50 delta and a recommendation (no set may drop by more than MAX_DROP)."""
    deltas = {
        name: round(new[name]["map50"] - previous[name]["map50"], 4)
        for name in new
        if name in previous
    }
    ok = (
        bool(deltas)
        and all(d >= -MAX_DROP for d in deltas.values())
        and any(d > 0 for d in deltas.values())
    )
    return {"deltas": deltas, "recommend_activate": ok}


def run_retrain(
    job: RetrainJob | None = None,
    *,
    epochs: int = 5,
    runner: Runner = subprocess_runner,
    work_dir: Path | None = None,
) -> ModelVersion:
    job = job or RetrainJob.objects.create(epochs=epochs)
    job.status = RetrainJob.Status.RUNNING
    job.save(update_fields=["status"])
    try:
        base = current_weights()
        if base is None:
            raise RuntimeError("No current layout model to fine-tune. Train one first (M6).")
        work = Path(work_dir or Path(settings.MEDIA_ROOT) / "retrain" / f"job{job.id}")
        feedback = work / "feedback"
        n = export_feedback(feedback)
        if n == 0:
            raise RuntimeError("No approved documents with layout regions to learn from yet.")
        out = work / "model"
        result = runner(
            {"feedback": str(feedback), "base": base, "out": str(out), "epochs": job.epochs}
        )
        parent = ModelVersion.objects.filter(path=base).first()
        cmp = compare(result["previous"], result["new"])
        version = ModelVersion.objects.create(
            name=f"layout-{timezone.now():%Y%m%d-%H%M%S}-j{job.id}",
            path=result["weights"],
            metrics={"new": result["new"], "previous": result["previous"], **cmp},
            parent=parent,
            n_feedback=n,
            notes=f"fine-tuned {job.epochs} epochs on {n} approved documents",
        )
        job.status, job.result, job.log = RetrainJob.Status.DONE, version, json.dumps(cmp)
    except Exception as exc:  # noqa: BLE001
        job.status, job.log = RetrainJob.Status.FAILED, str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save()
        raise
    job.finished_at = timezone.now()
    job.save()
    return version


@transaction.atomic
def activate(version: ModelVersion) -> ModelVersion:
    ModelVersion.objects.exclude(pk=version.pk).update(is_active=False)
    version.is_active = True
    version.save(update_fields=["is_active"])
    return version


def rollback() -> ModelVersion | None:
    """Re-activate the parent of the active model (or deactivate to fall back to the default)."""
    active = ModelVersion.objects.filter(is_active=True).first()
    if active is None:
        return None
    active.is_active = False
    active.save(update_fields=["is_active"])
    if active.parent_id:
        return activate(active.parent)
    return None
