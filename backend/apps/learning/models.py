from django.conf import settings
from django.db import models

from apps.documents.models import Document
from apps.workspaces.models import Workspace


class TrainingSample(models.Model):
    """A human-approved document turned into labelled data for the layout / extraction models."""

    document = models.OneToOneField(
        Document, null=True, on_delete=models.SET_NULL, related_name="training_sample"
    )
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="samples")
    image = models.ImageField(upload_to="training/%Y/%m/")
    regions = models.JSONField(default=list)  # [{cls, bbox:[x0,y0,x1,y1] normalised}]
    truth = models.JSONField(default=dict)  # effective (human-corrected) InvoiceExtraction
    field_boxes = models.JSONField(default=dict)  # {field: [x0,y0,x1,y1]}
    corrected = models.BooleanField(default=False)  # a human changed a value or a region
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ModelVersion(models.Model):
    """A trained layout model: weights on disk + the metrics that justify using it."""

    name = models.CharField(max_length=80, unique=True)
    path = models.CharField(max_length=500)
    metrics = models.JSONField(default=dict)  # {eval_set: {map50, per_class_ap50}}
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    n_feedback = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class RetrainJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    epochs = models.PositiveSmallIntegerField(default=5)
    log = models.TextField(blank=True)
    result = models.ForeignKey(ModelVersion, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
