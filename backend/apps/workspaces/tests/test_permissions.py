"""Permission matrix: anonymous / outsider / viewer / member / owner / API key / revoked key."""

import pytest
from django.test import override_settings

from apps.workspaces.models import Membership
from conftest import client_for

pytestmark = pytest.mark.django_db


def urls(ws):
    base = f"/api/v1/workspaces/{ws.id}"
    return {
        "detail": f"{base}/",
        "members": f"{base}/members/",
        "keys": f"{base}/api-keys/",
        "usage": f"{base}/usage/",
    }


# endpoint -> HTTP method -> minimum role that may call it
READ_ENDPOINTS = ["detail", "members", "usage"]


@pytest.mark.parametrize("name", READ_ENDPOINTS)
def test_reads_allowed_for_every_member_role(world, name):
    for who in ("owner", "member", "viewer"):
        res = client_for(world["users"][who]).get(urls(world["ws"])[name])
        assert res.status_code == 200, (who, name)


@pytest.mark.parametrize("name", [*READ_ENDPOINTS, "keys"])
def test_outsider_gets_404_and_anonymous_401(world, name):
    url = urls(world["ws"])[name]
    assert client_for(world["users"]["outsider"]).get(url).status_code == 404
    assert client_for().get(url).status_code == 401


def test_api_keys_list_owner_only(world):
    url = urls(world["ws"])["keys"]
    assert client_for(world["users"]["owner"]).get(url).status_code == 200
    assert client_for(world["users"]["member"]).get(url).status_code == 403
    assert client_for(world["users"]["viewer"]).get(url).status_code == 403


def test_owner_only_writes(world):
    u = urls(world["ws"])
    for who, expected in (("owner", 200), ("member", 403), ("viewer", 403)):
        res = client_for(world["users"][who]).patch(u["detail"], {"name": "New"}, format="json")
        assert res.status_code == expected, who
    for who in ("member", "viewer"):
        res = client_for(world["users"][who]).post(
            u["members"], {"email": "outsider@example.com"}, format="json"
        )
        assert res.status_code == 403, who
        res = client_for(world["users"][who]).post(u["keys"], {"name": "x"}, format="json")
        assert res.status_code == 403, who


def test_owner_can_add_change_and_remove_members(world):
    owner = client_for(world["users"]["owner"])
    u = urls(world["ws"])
    added = owner.post(
        u["members"], {"email": "outsider@example.com", "role": "viewer"}, format="json"
    )
    assert added.status_code == 201 and added.json()["role"] == "viewer"
    mid = added.json()["id"]
    assert (
        owner.patch(f"{u['members']}{mid}/", {"role": "member"}, format="json").json()["role"]
        == "member"
    )
    assert owner.delete(f"{u['members']}{mid}/").status_code == 204
    assert (
        owner.post(u["members"], {"email": "ghost@example.com"}, format="json").status_code == 400
    )


def test_cannot_remove_or_demote_last_owner(world):
    owner = client_for(world["users"]["owner"])
    mid = Membership.objects.get(user=world["users"]["owner"], workspace=world["ws"]).id
    u = urls(world["ws"])["members"]
    assert owner.delete(f"{u}{mid}/").status_code == 400
    assert owner.patch(f"{u}{mid}/", {"role": "member"}, format="json").status_code == 400


def test_member_of_other_workspace_cannot_touch_members_by_id(world):
    """A membership id from workspace A must not be reachable through workspace B's URL."""
    owner_b = client_for(world["users"]["outsider"])
    mid = Membership.objects.get(user=world["users"]["viewer"], workspace=world["ws"]).id
    res = owner_b.delete(f"/api/v1/workspaces/{world['other'].id}/members/{mid}/")
    assert res.status_code == 404
    assert Membership.objects.filter(id=mid).exists()


def test_workspace_list_only_shows_own_and_create_makes_owner(world):
    c = client_for(world["users"]["outsider"])
    assert [w["id"] for w in c.get("/api/v1/workspaces/").json()] == [world["other"].id]
    created = c.post("/api/v1/workspaces/", {"name": "Fresh"}, format="json")
    assert created.status_code == 201 and created.json()["role"] == "owner"


# ---- API keys -----------------------------------------------------------------


def test_api_key_is_shown_once_and_stored_hashed(world):
    owner = client_for(world["users"]["owner"])
    res = owner.post(urls(world["ws"])["keys"], {"name": "n8n"}, format="json")
    raw = res.json()["key"]
    assert raw.startswith("ds_")
    listed = owner.get(urls(world["ws"])["keys"]).json()
    assert all("key" not in k for k in listed)
    from apps.workspaces.models import ApiKey

    stored = ApiKey.objects.get(id=res.json()["id"])
    assert raw not in (stored.key_hash, stored.prefix) and len(stored.key_hash) == 64


def test_api_key_reads_own_workspace_as_member(world):
    c = client_for(api_key=world["raw_key"])
    u = urls(world["ws"])
    assert c.get(u["detail"]).status_code == 200
    assert c.get(u["usage"]).status_code == 200
    # member-level only: cannot manage keys/members or rename
    assert c.get(u["keys"]).status_code == 403
    assert c.post(u["members"], {"email": "x@example.com"}, format="json").status_code == 403
    assert c.patch(u["detail"], {"name": "Hax"}, format="json").status_code == 403


def test_api_key_cannot_reach_other_workspace_or_human_only_endpoints(world):
    c = client_for(api_key=world["raw_key"])
    assert c.get(urls(world["other"])["detail"]).status_code == 404
    assert c.get("/api/v1/workspaces/").status_code == 403
    assert c.get("/api/v1/me/").status_code == 403


def test_invalid_tampered_and_revoked_keys_rejected(world):
    u = urls(world["ws"])["detail"]
    assert client_for(api_key="garbage").get(u).status_code == 401
    tampered = world["raw_key"][:-3] + "xyz"
    assert client_for(api_key=tampered).get(u).status_code == 401
    world["key"].revoke()
    assert client_for(api_key=world["raw_key"]).get(u).status_code == 401


def test_owner_revokes_key_via_api(world):
    owner = client_for(world["users"]["owner"])
    res = owner.delete(f"{urls(world['ws'])['keys']}{world['key'].id}/")
    assert res.status_code == 204
    assert client_for(api_key=world["raw_key"]).get(urls(world["ws"])["detail"]).status_code == 401


def test_api_key_requests_are_counted_and_throttled(world):
    u = urls(world["ws"])
    with override_settings(
        DOCSENSE_THROTTLE_RATES={"auth": "99/min", "user": "99/min", "apikey": "3/min"}
    ):
        c = client_for(api_key=world["raw_key"])
        codes = [c.get(u["detail"]).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    summary = client_for(world["users"]["owner"]).get(u["usage"]).json()
    assert summary["today"]["api_requests"] == 5
