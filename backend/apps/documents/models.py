from django.conf import settings
from django.db import models

from apps.workspaces.models import Workspace


class Document(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        PROCESSING = "processing"
        NEEDS_REVIEW = "needs_review"
        DONE = "done"
        FAILED = "failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    file = models.FileField(upload_to="uploads/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    doc_type = models.CharField(max_length=30, default="invoice")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(blank=True)
    page_count = models.PositiveSmallIntegerField(default=0)
    progress = models.JSONField(default=dict, blank=True)  # {step: {status, detail, ts}}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Page(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="pages")
    number = models.PositiveSmallIntegerField()
    image = models.ImageField(upload_to="pages/%Y/%m/")  # cleaned page image
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    words = models.JSONField(default=list)  # [{text, bbox:[x0,y0,x1,y1] normalised, conf, page}]

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="uniq_page")]


class Extraction(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="extractions")
    version = models.PositiveIntegerField(default=1)
    data = models.JSONField(default=dict)  # raw schema output incl. line_items
    issues = models.JSONField(default=list)  # failed validation rules
    overall_confidence = models.FloatField(default=0.0)
    needs_review = models.BooleanField(default=False)
    provider = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["document", "version"], name="uniq_extraction_version")
        ]


class FieldValue(models.Model):
    extraction = models.ForeignKey(Extraction, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=40)
    value = models.TextField(blank=True)  # model output, stringified
    confidence = models.FloatField(default=0.0)
    flags = models.JSONField(default=list)
    page = models.PositiveSmallIntegerField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)  # normalised [x0,y0,x1,y1]
    reviewed_value = models.TextField(null=True, blank=True)  # human correction (M3)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["extraction", "name"], name="uniq_field")]
