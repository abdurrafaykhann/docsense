import pytest
from django.core.cache import cache
from django.test import override_settings

from conftest import client_for, make_user


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()


@override_settings(DEMO_READONLY=True)
def test_writes_are_refused_but_reads_and_login_work(db):
    make_user("a@example.com")
    c = client_for()
    r = c.post("/api/v1/auth/login/", {"email": "a@example.com", "password": "S3cure-pass!word"})
    assert r.status_code == 200
    assert c.post("/api/v1/auth/signup/", {"email": "n@example.com"}).status_code == 403
    assert c.get("/api/v1/health/").status_code == 200
    blocked = c.post("/api/v1/workspaces/1/documents/", {})
    assert blocked.status_code == 403 and blocked.json()["demo_readonly"] is True
    assert c.delete("/api/v1/workspaces/1/documents/1/").status_code == 403


@override_settings(DEMO_READONLY=True, DEMO_ASK_DAILY_CAP=2)
def test_ask_endpoints_pass_through_until_the_daily_cap(db):
    c = client_for()
    codes = [
        c.post("/api/v1/workspaces/1/chat/ask/", {"question": "x"}).status_code for _ in range(3)
    ]
    assert 403 not in codes[:2]  # reached the view (401/404), not blocked by the guard
    assert codes[2] == 429


def test_nothing_is_blocked_when_not_a_demo(db):
    c = client_for()
    assert "demo_readonly" not in c.post("/api/v1/workspaces/1/documents/", {}).content.decode()
