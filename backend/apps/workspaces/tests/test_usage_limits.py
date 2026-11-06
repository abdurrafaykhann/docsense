import pytest

from apps.workspaces import usage
from apps.workspaces.usage import FileTooLarge, UploadLimitExceeded, reserve_upload

pytestmark = pytest.mark.django_db


def test_reserve_upload_counts_files_and_bytes(world):
    ws = world["ws"]
    reserve_upload(ws, 1000)
    reserve_upload(ws, 500)
    assert usage.today_count(ws.id, usage.UPLOADS) == 2
    assert usage.today_count(ws.id, usage.UPLOAD_BYTES) == 1500


def test_daily_upload_limit_enforced_without_consuming_extra(world):
    ws = world["ws"]
    ws.daily_upload_limit = 2
    ws.save()
    reserve_upload(ws, 1)
    reserve_upload(ws, 1)
    with pytest.raises(UploadLimitExceeded):
        reserve_upload(ws, 1)
    assert usage.today_count(ws.id, usage.UPLOADS) == 2


def test_oversized_file_rejected_and_not_counted(world):
    ws = world["ws"]
    ws.max_upload_mb = 1
    ws.save()
    with pytest.raises(FileTooLarge):
        reserve_upload(ws, 2 * 1024 * 1024)
    assert usage.today_count(ws.id, usage.UPLOADS) == 0


def test_limits_are_per_workspace(world):
    a, b = world["ws"], world["other"]
    a.daily_upload_limit = 1
    a.save()
    reserve_upload(a, 1)
    reserve_upload(b, 1)  # unaffected by A's quota
    with pytest.raises(UploadLimitExceeded):
        reserve_upload(a, 1)


def test_usage_endpoint_reports_limits(world):
    from conftest import client_for

    reserve_upload(world["ws"], 10)
    data = (
        client_for(world["users"]["viewer"])
        .get(f"/api/v1/workspaces/{world['ws'].id}/usage/")
        .json()
    )
    assert data["today"]["uploads"] == 1
    assert data["limits"] == {"daily_uploads": 50, "max_upload_mb": 10}
