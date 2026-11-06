from django.db import models


class LLMCache(models.Model):
    """Responses cached by hash of (schema, prompt). Reprocessing the same doc costs 0 requests."""

    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class LLMUsage(models.Model):
    """One row per provider attempt, for the admin usage page and free-tier accounting."""

    provider = models.CharField(max_length=40)
    schema = models.CharField(max_length=80)
    status = models.CharField(max_length=20)  # ok | rate_limited | error | cache_hit
    latency_s = models.FloatField(default=0.0)
    attempt = models.PositiveSmallIntegerField(default=1)
    prompt_chars = models.PositiveIntegerField(default=0)
    workspace_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    document_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def tokens_est(self) -> int:
        return self.prompt_chars // 4
