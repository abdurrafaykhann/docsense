from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.workspaces.permissions import IsHumanUser

from . import services
from .models import ModelVersion, RetrainJob, TrainingSample
from .tasks import retrain_task


class IsStaffUser(BasePermission):
    """Platform admins only (model registry affects every workspace)."""

    def has_permission(self, request, view):
        return bool(IsHumanUser().has_permission(request, view) and request.user.is_staff)


def version_payload(v: ModelVersion) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "is_active": v.is_active,
        "created_at": v.created_at,
        "n_feedback": v.n_feedback,
        "notes": v.notes,
        "parent": v.parent.name if v.parent_id else None,
        "metrics": v.metrics,
    }


def job_payload(j: RetrainJob) -> dict:
    return {
        "id": j.id,
        "status": j.status,
        "epochs": j.epochs,
        "log": j.log,
        "result": version_payload(j.result) if j.result_id else None,
        "created_at": j.created_at,
        "finished_at": j.finished_at,
    }


class ModelList(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request):
        return Response(
            {
                "models": [
                    version_payload(v) for v in ModelVersion.objects.select_related("parent")
                ],
                "jobs": [job_payload(j) for j in RetrainJob.objects.select_related("result")[:10]],
                "feedback": {
                    "samples": TrainingSample.objects.count(),
                    "corrected": TrainingSample.objects.filter(corrected=True).count(),
                },
            }
        )


class Retrain(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request):
        epochs = int(request.data.get("epochs", 5))
        if not 1 <= epochs <= 50:
            raise ValidationError({"epochs": "Between 1 and 50."})
        if RetrainJob.objects.filter(status__in=["queued", "running"]).exists():
            raise ValidationError({"detail": "A retraining job is already running."})
        job = RetrainJob.objects.create(requested_by=request.user, epochs=epochs)
        retrain_task.delay(job.id)
        job.refresh_from_db()
        return Response(job_payload(job), status=status.HTTP_202_ACCEPTED)


class RetrainDetail(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, pk):
        return Response(job_payload(get_object_or_404(RetrainJob, pk=pk)))


class Activate(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        return Response(version_payload(services.activate(get_object_or_404(ModelVersion, pk=pk))))


class Rollback(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request):
        restored = services.rollback()
        return Response({"active": version_payload(restored) if restored else None})
