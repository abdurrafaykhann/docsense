from django.db import models

from apps.documents.models import Document
from apps.workspaces.models import Workspace


class UniversePoint(models.Model):
    """A document placed in 3D by its (UMAP-reduced) embedding."""

    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="universe")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="universe")
    x = models.FloatField()
    y = models.FloatField()
    z = models.FloatField()
    cluster = models.IntegerField(default=-1)  # -1 = unclustered
    cluster_label = models.CharField(max_length=120, blank=True)
    built_at = models.DateTimeField(auto_now=True)
