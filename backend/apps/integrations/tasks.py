from celery import shared_task

from . import webhooks
from .models import WebhookDelivery


@shared_task(name="integrations.deliver")
def deliver(delivery_id: int) -> int:
    d = WebhookDelivery.objects.select_related("endpoint").get(pk=delivery_id)
    if d.status == WebhookDelivery.Status.DELIVERED:
        return delivery_id
    ok = webhooks.attempt_delivery(d)
    if not ok and d.status == WebhookDelivery.Status.PENDING:
        delay = webhooks.BACKOFF[min(d.attempts - 1, len(webhooks.BACKOFF) - 1)]
        deliver.apply_async((delivery_id,), countdown=delay)  # inline when CELERY_EAGER
    return delivery_id
