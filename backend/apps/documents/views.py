import hashlib

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.pipeline.progress import initial_progress
from apps.pipeline.tasks import process_document
from apps.workspaces import usage
from apps.workspaces.models import Role
from apps.workspaces.views import WorkspaceScoped

from .models import Document, Extraction


def doc_summary(d: Document) -> dict:
    return {
        "id": d.id,
        "name": d.original_name,
        "status": d.status,
        "doc_type": d.doc_type,
        "page_count": d.page_count,
        "size": d.size,
        "created_at": d.created_at,
        "error": d.error,
    }


def extraction_payload(ext: Extraction | None) -> dict | None:
    if ext is None:
        return None
    return {
        "id": ext.id,
        "version": ext.version,
        "overall_confidence": ext.overall_confidence,
        "needs_review": ext.needs_review,
        "provider": ext.provider,
        "issues": ext.issues,
        "line_items": ext.data.get("line_items", []),
        "fields": [
            {
                "name": f.name,
                "value": f.value,
                "reviewed_value": f.reviewed_value,
                "confidence": f.confidence,
                "flags": f.flags,
                "page": f.page,
                "bbox": f.bbox,
            }
            for f in ext.fields.all().order_by("id")
        ],
    }


class DocumentList(WorkspaceScoped):
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, workspace_id):
        qs = Document.objects.filter(workspace_id=workspace_id)
        if st := request.query_params.get("status"):
            qs = qs.filter(status=st)
        if q := request.query_params.get("q"):
            qs = qs.filter(original_name__icontains=q)
        return Response([doc_summary(d) for d in qs[:200]])

    def post(self, request, workspace_id):
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            raise ValidationError({"files": "Upload at least one file."})
        ws = self.workspace()
        created = []
        errors = []
        for f in files:
            ctype = f.content_type
            if ctype not in settings.ALLOWED_UPLOAD_TYPES:
                errors.append({"name": f.name, "error": f"Unsupported type {ctype}"})
                continue
            try:
                with transaction.atomic():
                    usage.reserve_upload(ws, f.size)
                    data = f.read()
                    f.seek(0)
                    doc = Document.objects.create(
                        workspace=ws,
                        uploader=None if request.auth else request.user,
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
        code = status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST
        for d in created:
            d.refresh_from_db()
        return Response(
            {"documents": [doc_summary(d) for d in created], "errors": errors}, status=code
        )


class DocumentDetail(WorkspaceScoped):
    def required_role(self, request):
        return Role.MEMBER if request.method == "DELETE" else Role.VIEWER

    def _doc(self, workspace_id, pk) -> Document:
        return get_object_or_404(Document, pk=pk, workspace_id=workspace_id)

    def get(self, request, workspace_id, pk):
        d = self._doc(workspace_id, pk)
        ext = d.extractions.first()
        return Response(
            {
                **doc_summary(d),
                "progress": d.progress,
                "pages": [
                    {"number": p.number, "width": p.width, "height": p.height}
                    for p in d.pages.all()
                ],
                "extraction": extraction_payload(ext),
            }
        )

    def delete(self, request, workspace_id, pk):
        self._doc(workspace_id, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentReprocess(WorkspaceScoped):
    def post(self, request, workspace_id, pk):
        d = get_object_or_404(Document, pk=pk, workspace_id=workspace_id)
        d.status = Document.Status.QUEUED
        d.progress = initial_progress()
        d.save(update_fields=["status", "progress", "updated_at"])
        process_document.delay(d.id)
        d.refresh_from_db()
        return Response(doc_summary(d), status=status.HTTP_202_ACCEPTED)


class PageImage(WorkspaceScoped):
    def get(self, request, workspace_id, pk, number):
        d = get_object_or_404(Document, pk=pk, workspace_id=workspace_id)
        page = get_object_or_404(d.pages, number=number)
        return FileResponse(page.image.open("rb"), content_type="image/jpeg")
