"""Orchestrates the pipeline for one document (load, cleanup, OCR, extract, validate, save)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.documents.models import Document, Extraction, FieldValue, Page
from apps.documents.models import Region as RegionRow
from apps.llm import context as llm_context
from apps.validation.schema import NUMERIC_FIELDS

from . import core, services
from .loader import encode_jpeg, load_pages
from .progress import initial_progress, publish

log = logging.getLogger(__name__)


def _fmt(name: str, value) -> str:
    if value is None:
        return ""
    if name in NUMERIC_FIELDS:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    return str(value)


_UNSET = object()


def run_pipeline(document_id: int, *, ocr=None, llm=None, layout=_UNSET) -> Document:
    doc = Document.objects.select_related("workspace").get(pk=document_id)
    ocr = ocr or services.get_ocr()
    llm = llm or services.get_llm()
    layout = services.get_layout() if layout is _UNSET else layout
    doc.status = Document.Status.PROCESSING
    doc.error = ""
    doc.progress = initial_progress()
    doc.save(update_fields=["status", "error", "progress", "updated_at"])
    step = "load"
    try:
        with llm_context.usage_context(workspace_id=doc.workspace_id, document_id=doc.id):
            publish(doc, "load", "running")
            with doc.file.open("rb") as fh:
                images = load_pages(fh.read(), doc.content_type, settings.MAX_PAGES_PER_DOC)
            publish(doc, "load", "done", f"{len(images)} page(s)")

            def on_step(name: str, status: str, detail: str = "") -> None:
                nonlocal step
                step = name
                publish(doc, name, status, detail)

            res = core.process(
                images,
                ocr,
                llm,
                max_chars=settings.LLM_MAX_PROMPT_CHARS,
                on_step=on_step,
                layout=layout,
            )
            provider = getattr(getattr(llm, "providers", [None])[0], "name", "") or ""

            step = "save"
            publish(doc, "save", "running")
            _persist(doc, res, provider)
            publish(doc, "save", "done", "needs review" if res.needs_review else "ok")
            from apps.rag.service import index_quietly

            index_quietly(doc)
    except Exception as exc:  # noqa: BLE001
        log.exception("pipeline failed for document %s at %s", document_id, step)
        doc.status = Document.Status.FAILED
        doc.error = f"{step}: {exc}"[:2000]
        publish(doc, step, "failed", str(exc)[:200])
    return doc


@transaction.atomic
def _persist(doc, res, provider):
    cleaned, words_by_page, inv = res.cleaned, res.words_by_page, res.invoice
    issues, scores, overall, review = res.issues, res.scores, res.overall, res.needs_review
    Page.objects.filter(document=doc).delete()
    for i, img in enumerate(cleaned, start=1):
        page = Page(
            document=doc,
            number=i,
            width=img.shape[1],
            height=img.shape[0],
            words=[w.as_dict() for w in words_by_page.get(i, [])],
        )
        page.image.save(f"{doc.id}-{i}.jpg", ContentFile(encode_jpeg(img)), save=True)
        RegionRow.objects.bulk_create(
            RegionRow(page=page, cls=r.cls, bbox=r.bbox, score=r.score, source="model")
            for r in res.regions_by_page.get(i, [])
        )

    version = (
        doc.extractions.order_by("-version").values_list("version", flat=True).first() or 0
    ) + 1
    ext = Extraction.objects.create(
        document=doc,
        version=version,
        data=inv.model_dump(mode="json"),
        issues=[i.as_dict() for i in issues],
        overall_confidence=overall,
        needs_review=review,
        provider=provider,
    )
    FieldValue.objects.bulk_create(
        FieldValue(
            extraction=ext,
            name=s.name,
            value=_fmt(s.name, s.value) if s.name != "line_items" else f"{len(s.value)} items",
            confidence=s.confidence,
            flags=s.flags,
            page=s.location.page if s.location else None,
            bbox=s.location.bbox if s.location else None,
        )
        for s in scores
    )
    if cleaned:
        import imagehash
        from PIL import Image

        doc.phash = str(imagehash.phash(Image.fromarray(cleaned[0])))
        doc.save(update_fields=["phash"])
    doc.page_count = len(cleaned)
    doc.status = Document.Status.NEEDS_REVIEW if review else Document.Status.DONE
    doc.save(update_fields=["page_count", "status", "updated_at"])
