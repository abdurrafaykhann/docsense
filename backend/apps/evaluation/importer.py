"""Import result JSON files written by ml/ scripts into EvalRun rows (idempotent)."""

from __future__ import annotations

import json
from pathlib import Path

from django.utils.dateparse import parse_datetime
from django.utils.timezone import now

from .models import EvalRun


def compact_docs(docs: list[dict], limit: int = 200) -> list[dict]:
    """Keep what the UI needs to show failures; drop bulky raw predictions."""
    out = []
    for d in docs[:limit]:
        score = d.get("score", {})
        wrong = [
            name
            for name, c in score.get("fields", {}).items()
            if c["truth"] and not c["tp"] or (c["pred"] and not c["truth"])
        ]
        out.append(
            {
                "id": d.get("id"),
                "needs_review": d.get("needs_review"),
                "issues": d.get("issues", []),
                "wrong_fields": wrong,
                "error": d.get("error"),
            }
        )
    return out


def import_file(path: Path) -> tuple[EvalRun, bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    run, created = EvalRun.objects.update_or_create(
        source=path.name,
        defaults={
            "kind": payload.get("kind", "extraction"),
            "dataset": payload.get("dataset", ""),
            "arm": payload.get("arm", ""),
            "n": payload.get("n", 0),
            "metrics": payload.get("metrics", {}),
            "config": {k: payload[k] for k in ("ocr", "ocr_cache") if k in payload},
            "docs": compact_docs(payload.get("docs", [])),
            "git_sha": payload.get("git_sha", ""),
            "created_at": parse_datetime(payload.get("created_at", "")) or now(),
        },
    )
    return run, created
