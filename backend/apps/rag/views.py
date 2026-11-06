from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.documents.models import Document
from apps.pipeline import services as pipeline_services
from apps.workspaces.models import Role
from apps.workspaces.views import WorkspaceScoped

from . import service
from .models import Conversation, Message


class Ask(WorkspaceScoped):
    def required_role(self, request):
        return Role.VIEWER  # asking questions is a read operation

    def post(self, request, workspace_id):
        question = (request.data.get("question") or "").strip()
        if not question or len(question) > 1000:
            raise ValidationError({"question": "Ask a question (max 1000 characters)."})
        ids = request.data.get("document_ids") or None
        if ids is not None and (
            not isinstance(ids, list) or not all(isinstance(i, int) for i in ids)
        ):
            raise ValidationError({"document_ids": "Expected a list of document ids."})
        conv = None
        if cid := request.data.get("conversation_id"):
            conv = get_object_or_404(Conversation, pk=cid, workspace_id=workspace_id)
        if conv is None:
            conv = Conversation.objects.create(
                workspace_id=workspace_id,
                user=None if request.auth else request.user,
                title=question[:120],
            )
        result = service.ask(workspace_id, question, pipeline_services.get_llm(), document_ids=ids)
        Message.objects.create(conversation=conv, role="user", content=question)
        Message.objects.create(
            conversation=conv,
            role="assistant",
            content=result["answer"],
            grounded=result["grounded"],
            citations=result["citations"],
        )
        return Response({"conversation_id": conv.id, **result})


class ConversationList(WorkspaceScoped):
    def get(self, request, workspace_id):
        rows = Conversation.objects.filter(workspace_id=workspace_id)[:50]
        return Response([{"id": c.id, "title": c.title, "created_at": c.created_at} for c in rows])


class ConversationDetail(WorkspaceScoped):
    def get(self, request, workspace_id, pk):
        conv = get_object_or_404(Conversation, pk=pk, workspace_id=workspace_id)
        return Response(
            {
                "id": conv.id,
                "title": conv.title,
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "grounded": m.grounded,
                        "citations": m.citations,
                    }
                    for m in conv.messages.all()
                ],
            }
        )


class Reindex(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER

    def post(self, request, workspace_id):
        docs = Document.objects.filter(workspace_id=workspace_id).exclude(pages=None)
        n = sum(service.index_document(d) for d in docs.distinct())
        return Response(
            {"documents": docs.distinct().count(), "chunks": n}, status=status.HTTP_200_OK
        )
