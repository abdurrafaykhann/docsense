from django.db import models


class EvalRun(models.Model):
    """One evaluation result (extraction / layout / rag) produced by ml/ scripts."""

    kind = models.CharField(max_length=20)  # extraction | layout | rag
    dataset = models.CharField(max_length=80)
    arm = models.CharField(max_length=200)
    n = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(default=dict)
    config = models.JSONField(default=dict)
    docs = models.JSONField(default=list)  # compact per-document outcomes
    git_sha = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=200, unique=True)  # result file name (idempotent import)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-id"]
