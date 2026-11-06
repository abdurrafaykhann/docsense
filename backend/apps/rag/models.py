from django.conf import settings
from django.db import models

from apps.documents.models import Document
from apps.workspaces.models import Workspace


class Chunk(models.Model):
    """A retrievable passage that remembers where it came from (page + bounding box)."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="chunks")
    kind = models.CharField(max_length=10, default="text")  # text | summary
    page = models.PositiveSmallIntegerField(default=1)
    position = models.PositiveIntegerField(default=0)
    text = models.TextField()
    bbox = models.JSONField(default=list)  # normalised [x0, y0, x1, y1] of the source words
    embedder = models.CharField(max_length=60)
    embedding = models.BinaryField()  # float32, L2-normalised
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["workspace", "embedder"])]
        ordering = ["document_id", "position"]


class Conversation(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="conversations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10)  # user | assistant
    content = models.TextField()
    grounded = models.BooleanField(default=True)
    citations = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
