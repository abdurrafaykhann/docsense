from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.pipeline import services as pipeline_services
from apps.rag import service as rag_service
from apps.workspaces.models import Role
from apps.workspaces.views import WorkspaceScoped

from .graph import run_agent


def search_tool(workspace_id: int, question: str) -> list[dict]:
    hits = rag_service.retrieve(workspace_id, question)
    return [
        {"document": h["chunk"].document.original_name, "page": h["chunk"].page,
         "text": h["chunk"].text[:300]}
        for h in hits
    ]  # fmt: skip


class AgentAsk(WorkspaceScoped):
    def required_role(self, request):
        return Role.VIEWER  # read-only analysis

    def post(self, request, workspace_id):
        question = (request.data.get("question") or "").strip()
        if not question or len(question) > 1000:
            raise ValidationError({"question": "Ask a question (max 1000 characters)."})
        result = run_agent(question, workspace_id, pipeline_services.get_llm(), search_tool)
        return Response(result)
