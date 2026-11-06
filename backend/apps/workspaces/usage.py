"""Usage counters and upload limits."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import APIException

from .models import UsageCounter, Workspace

UPLOADS = "uploads"
UPLOAD_BYTES = "upload_bytes"
API_REQUESTS = "api_requests"


class UploadLimitExceeded(APIException):
    status_code = 429
    default_code = "upload_limit_exceeded"
    default_detail = "Daily upload limit reached for this workspace."


class FileTooLarge(APIException):
    status_code = 413
    default_code = "file_too_large"
    default_detail = "File exceeds the workspace upload size limit."


def bump(workspace_id: int, metric: str, amount: int = 1) -> None:
    day = timezone.localdate()
    counter, created = UsageCounter.objects.get_or_create(
        workspace_id=workspace_id, day=day, metric=metric, defaults={"count": amount}
    )
    if not created:
        UsageCounter.objects.filter(pk=counter.pk).update(count=F("count") + amount)


def today_count(workspace_id: int, metric: str) -> int:
    row = UsageCounter.objects.filter(
        workspace_id=workspace_id, day=timezone.localdate(), metric=metric
    ).first()
    return row.count if row else 0


@transaction.atomic
def reserve_upload(workspace: Workspace, size_bytes: int) -> None:
    """Call before accepting a file. Raises if the size or daily quota is exceeded."""
    if size_bytes > workspace.max_upload_mb * 1024 * 1024:
        raise FileTooLarge(f"Max file size is {workspace.max_upload_mb} MB.")
    if today_count(workspace.id, UPLOADS) >= workspace.daily_upload_limit:
        raise UploadLimitExceeded()
    bump(workspace.id, UPLOADS)
    bump(workspace.id, UPLOAD_BYTES, size_bytes)


def usage_summary(workspace: Workspace, days: int = 30) -> dict:
    since = timezone.localdate() - timezone.timedelta(days=days - 1)
    history: dict[str, dict[str, int]] = {}
    for row in UsageCounter.objects.filter(workspace=workspace, day__gte=since).order_by("day"):
        history.setdefault(row.day.isoformat(), {})[row.metric] = row.count
    return {
        "today": {
            "uploads": today_count(workspace.id, UPLOADS),
            "upload_bytes": today_count(workspace.id, UPLOAD_BYTES),
            "api_requests": today_count(workspace.id, API_REQUESTS),
        },
        "limits": {
            "daily_uploads": workspace.daily_upload_limit,
            "max_upload_mb": workspace.max_upload_mb,
        },
        "history": history,
    }
