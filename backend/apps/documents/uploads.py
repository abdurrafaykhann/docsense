"""Accept uploaded files: validate, enforce workspace limits, store, start the pipeline."""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import transaction

from apps.pipeline.progress import initial_progress
from apps.pipeline.tasks import process_document
from apps.workspaces import usage

from .models import Document


def create_documents(workspace, files, uploader=None) -> tuple[list[Document], list[dict]]:
    """Returns (created documents, per-file errors). Shared by UI upload and inbound API."""
    created: list[Document] = []
    errors: list[dict] = []
    for f in files:
        ctype = f.content_type
        if ctype not in settings.ALLOWED_UPLOAD_TYPES:
            errors.append({"name": f.name, "error": f"Unsupported type {ctype}"})
            continue
        try:
            with transaction.atomic():
                usage.reserve_upload(workspace, f.size)
                data = f.read()
                f.seek(0)
                doc = Document.objects.create(
                    workspace=workspace,
                    uploader=uploader,
                    file=f,
                    original_name=f.name[:255],
                    content_type=ctype,
                    size=f.size,
                    sha256=hashlib.sha256(data).hexdigest(),
                    progress=initial_progress(),
                )
        except (usage.UploadLimitExceeded, usage.FileTooLarge) as exc:
            errors.append({"name": f.name, "error": str(exc.detail)})
            continue
        created.append(doc)
        process_document.delay(doc.id)
    for d in created:
        d.refresh_from_db()
    return created, errors
