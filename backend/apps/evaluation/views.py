from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.workspaces.permissions import IsHumanUser

from .models import EvalRun


def summary(r: EvalRun) -> dict:
    return {
        "id": r.id,
        "kind": r.kind,
        "dataset": r.dataset,
        "arm": r.arm,
        "n": r.n,
        "git_sha": r.git_sha,
        "created_at": r.created_at,
        "config": r.config,
        "metrics": r.metrics,
    }


class RunList(APIView):
    """Project-level results (not tenant data), readable by any signed-in user."""

    permission_classes = [IsHumanUser]

    def get(self, request):
        qs = EvalRun.objects.all()
        if kind := request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        return Response([summary(r) for r in qs[:100]])


class RunDetail(APIView):
    permission_classes = [IsHumanUser]

    def get(self, request, pk):
        r = get_object_or_404(EvalRun, pk=pk)
        return Response({**summary(r), "docs": r.docs})
