import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.workspaces.models import ApiKey, Membership, Role, Workspace


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def make_user(email: str) -> User:
    return User.objects.create_user(email, "S3cure-pass!word")


def client_for(user: User | None = None, api_key: str | None = None) -> APIClient:
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    if api_key:
        c.credentials(HTTP_X_API_KEY=api_key)
    return c


@pytest.fixture
def world(db):
    """Two workspaces; ws has owner/member/viewer, other has its own owner, plus an outsider."""
    ws = Workspace.create_unique("Acme Traders")
    other = Workspace.create_unique("Other Co")
    users = {n: make_user(f"{n}@example.com") for n in ("owner", "member", "viewer", "outsider")}
    Membership.objects.create(user=users["owner"], workspace=ws, role=Role.OWNER)
    Membership.objects.create(user=users["member"], workspace=ws, role=Role.MEMBER)
    Membership.objects.create(user=users["viewer"], workspace=ws, role=Role.VIEWER)
    Membership.objects.create(user=users["outsider"], workspace=other, role=Role.OWNER)
    key, raw = ApiKey.issue(ws, "ci", created_by=users["owner"])
    return {"ws": ws, "other": other, "users": users, "key": key, "raw_key": raw}
