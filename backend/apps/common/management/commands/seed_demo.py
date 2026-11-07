"""Load the committed demo pack (seed/demo_workspace) into a ready-to-demo workspace.

No OCR, no LLM, no internet: word/region/field boxes and truth come from the pack.

    python manage.py seed_demo            # idempotent: does nothing if the demo already exists
    python manage.py seed_demo --reset    # wipe and rebuild the demo workspace
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import imagehash
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from apps.analytics.service import run_detectors
from apps.documents import review
from apps.documents.models import Document, Extraction, FieldValue, Page
from apps.documents.models import Region as RegionRow
from apps.pipeline.progress import STEPS
from apps.rag.service import index_document
from apps.universe import service as universe
from apps.validation import rules
from apps.validation.schema import NUMERIC_FIELDS, SCALAR_FIELDS, InvoiceExtraction
from apps.workspaces.models import Membership, Role, Workspace

SLUG = "demo-traders"


def fmt(name: str, value) -> str:
    if value is None:
        return ""
    if name in NUMERIC_FIELDS:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    return str(value)


class Command(BaseCommand):
    help = "Seed the demo workspace (about 50 sample documents) and the demo login."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--no-universe", action="store_true", help="skip the UMAP step")

    def handle(self, *args, **opts):
        pack = Path(settings.SEED_DIR)
        if not (pack / "manifest.json").exists():
            raise CommandError(f"Demo pack not found at {pack} (set SEED_DIR).")
        existing = Workspace.objects.filter(slug=SLUG).first()
        if existing and not opts["reset"]:
            self.stdout.write("demo workspace already seeded (use --reset to rebuild)")
            return
        if existing:
            existing.delete()

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=settings.DEMO_EMAIL, defaults={"name": "Demo User", "is_staff": True}
        )
        user.set_password(settings.DEMO_PASSWORD)
        user.is_staff = True
        user.save()
        ws = Workspace.objects.create(
            name="Demo Traders (sample data)", slug=SLUG, is_demo=True, daily_upload_limit=10
        )
        Membership.objects.create(user=user, workspace=ws, role=Role.OWNER)

        rows = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
        approved: list[Document] = []
        try:
            for row in rows:
                doc = self.create_document(ws, user, pack, row)
                if doc.status == Document.Status.DONE:
                    approved.append(doc)

            for doc in approved:
                index_document(doc)
            for doc in Document.objects.filter(workspace=ws, status=Document.Status.NEEDS_REVIEW):
                index_document(doc)
            flags = run_detectors(ws.id)
            placed = {"points": 0}
            if not opts["no_universe"]:
                placed = universe.rebuild(ws.id)
        except BaseException:
            # A half-seeded workspace would be reported as "already seeded" forever.
            ws.delete()
            raise
        self.stdout.write(
            self.style.SUCCESS(
                f"seeded {len(rows)} documents ({len(approved)} approved, "
                f"{len(rows) - len(approved)} awaiting review), {flags['flags']} flags, "
                f"{placed['points']} universe points. Login: {settings.DEMO_EMAIL}"
            )
        )

    # ------------------------------------------------------------------------------
    def create_document(self, ws, user, pack: Path, row: dict) -> Document:
        raw = (pack / row["file"]).read_bytes()
        truth = row["truth"]
        img = Image.open(io.BytesIO(raw))
        name = f"{truth['vendor_name']} {truth['invoice_number']}" + (
            " (copy).jpg" if row["planted"] == "exact_dup" else ".jpg"
        )
        import hashlib

        doc = Document(
            workspace=ws,
            uploader=user,
            original_name=name,
            content_type="image/jpeg",
            size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            phash=str(imagehash.phash(img.convert("RGB"))),
            page_count=1,
            status=Document.Status.PROCESSING,
            progress={s: {"status": "done", "detail": "seeded"} for s in STEPS},
        )
        doc.file.save(row["name"], ContentFile(raw), save=True)
        page = Page(document=doc, number=1, width=img.width, height=img.height, words=row["words"])
        page.image.save(row["name"], ContentFile(raw), save=True)
        RegionRow.objects.bulk_create(
            RegionRow(page=page, cls=r["cls"], bbox=r["bbox"], score=0.97, source="model")
            for r in row["regions"]
        )

        data = dict(truth)
        wrong = row["extracted_total_wrong"]
        if wrong:  # simulate an extraction mistake the validators catch and a human must fix
            data["total"] = round(truth["total"] + 100, 2)
        inv = InvoiceExtraction.model_validate(data)
        issues = rules.validate(inv)
        ext = Extraction.objects.create(
            document=doc,
            version=1,
            data=inv.model_dump(mode="json"),
            issues=[i.as_dict() for i in issues],
            overall_confidence=0.41 if wrong else 0.96,
            needs_review=wrong,
            provider="seed",
        )
        boxes = row["fields"]
        FieldValue.objects.bulk_create(
            FieldValue(
                extraction=ext,
                name=name_,
                value=fmt(name_, getattr(inv, name_)),
                confidence=0.3 if (wrong and name_ == "total") else 0.96,
                flags=["total_mismatch"] if (wrong and name_ == "total") else [],
                page=1 if name_ in boxes else None,
                bbox=boxes.get(name_),
            )
            for name_ in SCALAR_FIELDS
        )
        FieldValue.objects.create(
            extraction=ext, name="line_items", value=f"{len(inv.line_items)} items", confidence=1.0
        )
        if wrong:
            doc.status = Document.Status.NEEDS_REVIEW
            doc.save(update_fields=["status"])
        else:
            review.approve(ext, user, side_effects=False)
        doc.refresh_from_db()
        return doc
