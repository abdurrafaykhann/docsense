from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.documents.uploads import create_documents
from apps.documents.views import doc_summary, extraction_payload
from apps.workspaces.auth import ApiKeyAuthentication, ApiKeyPrincipal
from apps.workspaces.models import Role
from apps.workspaces.views import WorkspaceScoped

from . import webhooks
from .models import EVENTS, WebhookDelivery, WebhookEndpoint
from .payloads import processed_payload


def endpoint_payload(e: WebhookEndpoint, with_secret: bool = False) -> dict:
    data = {
        "id": e.id,
        "url": e.url,
        "events": e.events,
        "active": e.active,
        "created_at": e.created_at,
    }
    if with_secret:
        data["secret"] = e.secret  # shown exactly once, at creation
    return data


def delivery_payload(d: WebhookDelivery) -> dict:
    return {
        "id": d.id, "event": d.event, "status": d.status, "attempts": d.attempts,
        "response_code": d.response_code, "error": d.error, "created_at": d.created_at,
    }  # fmt: skip


class _OwnerOnly(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER


class WebhookList(_OwnerOnly):
    def get(self, request, workspace_id):
        rows = WebhookEndpoint.objects.filter(workspace_id=workspace_id).order_by("-id")
        return Response([endpoint_payload(e) for e in rows])

    def post(self, request, workspace_id):
        url = (request.data.get("url") or "").strip()
        events = request.data.get("events") or []
        if not isinstance(events, list) or any(e not in EVENTS for e in events):
            raise ValidationError({"events": f"Choose from {EVENTS}."})
        ok, why = webhooks.is_safe_url(url)
        if not ok:
            raise ValidationError({"url": why})
        ep = WebhookEndpoint.objects.create(
            workspace_id=workspace_id, url=url, events=events, secret=WebhookEndpoint.new_secret()
        )
        return Response(endpoint_payload(ep, with_secret=True), status=status.HTTP_201_CREATED)


class WebhookDetail(_OwnerOnly):
    def delete(self, request, workspace_id, pk):
        get_object_or_404(WebhookEndpoint, pk=pk, workspace_id=workspace_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookDeliveries(_OwnerOnly):
    def get(self, request, workspace_id, pk):
        ep = get_object_or_404(WebhookEndpoint, pk=pk, workspace_id=workspace_id)
        return Response([delivery_payload(d) for d in ep.deliveries.all()[:25]])


class WebhookTest(_OwnerOnly):
    def post(self, request, workspace_id, pk):
        from .tasks import deliver

        ep = get_object_or_404(WebhookEndpoint, pk=pk, workspace_id=workspace_id)
        d = WebhookDelivery.objects.create(
            endpoint=ep, event="ping", payload={"event": "ping", "workspace_id": workspace_id}
        )
        deliver.delay(d.id)
        d.refresh_from_db()
        return Response(delivery_payload(d), status=status.HTTP_202_ACCEPTED)


# --------------------------------------------------------------------------- inbound API
class _ApiKeyView(APIView):
    """Machine endpoints: workspace is derived from the API key, never from the URL."""

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def workspace(self, request):
        if not isinstance(request.user, ApiKeyPrincipal):
            raise PermissionDenied("API key required.")
        return request.auth.workspace


class Inbound(_ApiKeyView):
    """n8n / email-to-DocSense: POST files (+ optional source metadata) with an API key."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        ws = self.workspace(request)
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            raise ValidationError({"files": "Send at least one file as multipart 'files'."})
        created, errors = create_documents(ws, files, uploader=None)
        meta = {k: request.data.get(k, "")[:200] for k in ("source", "sender", "subject")}
        return Response(
            {
                "documents": [
                    {**doc_summary(d), "status_url": f"/api/v1/integrations/documents/{d.id}/"}
                    for d in created
                ],
                "errors": errors,
                "meta": meta,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
        )  # fmt: skip


class InboundDocument(_ApiKeyView):
    def get(self, request, pk):
        ws = self.workspace(request)
        d = get_object_or_404(Document, pk=pk, workspace=ws)
        return Response(
            {**doc_summary(d), "extraction": extraction_payload(d.extractions.first()),
             "webhook_payload": processed_payload(d)}
        )  # fmt: skip
