import secrets

from django.db import models

from apps.workspaces.models import Workspace

EVENTS = ["document.processed", "document.flagged", "ping"]


class WebhookEndpoint(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="webhooks")
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=80)  # HMAC key (must be recoverable to sign payloads)
    events = models.JSONField(default=list)  # subset of EVENTS; empty = all
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def new_secret() -> str:
        return "whsec_" + secrets.token_urlsafe(24)

    def wants(self, event: str) -> bool:
        return self.active and (not self.events or event in self.events)


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        DELIVERED = "delivered"
        FAILED = "failed"

    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    event = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
