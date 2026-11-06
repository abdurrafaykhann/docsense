"""Signed outbound webhooks with retry and SSRF protection."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from collections.abc import Callable
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone

from .models import WebhookDelivery, WebhookEndpoint

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
TIMEOUT = 10
BACKOFF = [30, 300]  # seconds before attempt 2 and 3


# ------------------------------------------------------------------------------ signing
def sign(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over `<timestamp>.<body>`; receivers should also reject old timestamps."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str, body: bytes, signature: str, tolerance: int = 300) -> bool:
    if abs(time.time() - float(timestamp)) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


# ------------------------------------------------------------------------------ SSRF guard
Resolver = Callable[[str], list[str]]


def default_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def is_safe_url(url: str, resolver: Resolver = default_resolver) -> tuple[bool, str]:
    """Reject non-https URLs and hosts resolving to private/loopback/link-local ranges."""
    parsed = urlparse(url)
    allow_private = getattr(settings, "WEBHOOKS_ALLOW_PRIVATE", False)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return False, "URL must be http(s) with a host"
    if parsed.scheme == "http" and not allow_private:
        return False, "Webhook URLs must use https"
    if allow_private:
        return True, ""
    try:
        addrs = resolver(parsed.hostname)
    except OSError:
        return False, "Host could not be resolved"
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Host resolves to a non-public address ({a})"
    return True, ""


# ------------------------------------------------------------------------------ delivery
Sender = Callable[[str, bytes, dict], tuple[int, str]]


def http_sender(url: str, body: bytes, headers: dict) -> tuple[int, str]:
    r = requests.post(url, data=body, headers=headers, timeout=TIMEOUT, allow_redirects=False)
    return r.status_code, r.text[:200]


def attempt_delivery(
    delivery: WebhookDelivery, sender: Sender = http_sender, resolver: Resolver = default_resolver
) -> bool:
    """One delivery attempt. Returns True when the receiver answered 2xx."""
    ep = delivery.endpoint
    body = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True).encode()
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DocSense-Webhooks/1",
        "X-DocSense-Event": delivery.event,
        "X-DocSense-Delivery": str(delivery.id),
        "X-DocSense-Timestamp": ts,
        "X-DocSense-Signature": sign(ep.secret, ts, body),
    }
    delivery.attempts += 1
    delivery.last_attempt_at = timezone.now()
    ok, why = is_safe_url(ep.url, resolver)
    code, error = None, ""
    if not ok:
        error = why
    else:
        try:
            code, text = sender(ep.url, body, headers)
            if not 200 <= code < 300:
                error = f"HTTP {code}: {text}"[:300]
        except Exception as exc:  # noqa: BLE001 - network errors are retried
            error = f"{type(exc).__name__}: {exc}"[:300]
    delivery.response_code = code
    delivery.error = error
    success = not error
    delivery.status = (
        WebhookDelivery.Status.DELIVERED
        if success
        else (
            WebhookDelivery.Status.FAILED
            if delivery.attempts >= MAX_ATTEMPTS
            else WebhookDelivery.Status.PENDING
        )
    )
    delivery.save()
    return success


def emit(workspace_id: int, event: str, payload: dict) -> list[WebhookDelivery]:
    """Create a delivery per subscribed endpoint and queue it (Celery; inline when eager)."""
    from .tasks import deliver

    out = []
    for ep in WebhookEndpoint.objects.filter(workspace_id=workspace_id, active=True):
        if not ep.wants(event):
            continue
        d = WebhookDelivery.objects.create(
            endpoint=ep,
            event=event,
            payload={"event": event, "created_at": timezone.now().isoformat(), **payload},
        )
        deliver.delay(d.id)
        out.append(d)
    return out


def emit_quietly(workspace_id: int, event: str, payload: dict) -> None:
    try:
        emit(workspace_id, event, payload)
    except Exception:  # noqa: BLE001 - integrations must never break processing
        log.exception("webhook emit failed (%s)", event)
