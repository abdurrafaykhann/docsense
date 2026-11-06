from django.conf import settings
from django.db import models

from apps.documents.models import Document
from apps.workspaces.models import Workspace


class Flag(models.Model):
    """A suspicious or duplicate document, with the evidence that raised it."""

    KINDS = ["exact_dup", "near_dup", "image_dup", "amount_outlier", "price_creep"]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="flags")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="flags")
    kind = models.CharField(max_length=20)
    severity = models.CharField(max_length=10, default="medium")
    evidence = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "kind"], name="uniq_flag")]
        ordering = ["resolved", "-created_at", "-id"]
