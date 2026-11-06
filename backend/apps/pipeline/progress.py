"""Step progress: persisted on the Document and broadcast over Channels."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

log = logging.getLogger(__name__)

STEPS = ["load", "cleanup", "ocr", "extract", "validate", "save"]


def group_name(document_id: int) -> str:
    return f"doc.{document_id}"


def initial_progress() -> dict:
    return {s: {"status": "pending", "detail": ""} for s in STEPS}


def snapshot(document) -> dict:
    return {
        "document_id": document.id,
        "doc_status": document.status,
        "steps": document.progress or initial_progress(),
    }


def publish(document, step: str, status: str, detail: str = "") -> None:
    """status: running | done | failed | skipped."""
    progress = document.progress or initial_progress()
    progress[step] = {"status": status, "detail": detail, "ts": timezone.now().isoformat()}
    document.progress = progress
    document.save(update_fields=["progress", "status", "error", "updated_at"])
    try:
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(
                group_name(document.id),
                {
                    "type": "progress",
                    "payload": {
                        "document_id": document.id,
                        "doc_status": document.status,
                        "step": step,
                        "status": status,
                        "detail": detail,
                    },
                },
            )
    except Exception:  # noqa: BLE001 - a Redis outage must never fail processing
        log.warning("progress broadcast failed", exc_info=True)
