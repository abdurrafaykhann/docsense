import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.workspaces.models import Membership, Role

pytestmark = pytest.mark.django_db
SIGNUP = "/api/v1/auth/signup/"


def signup(client, email="a@example.com", **extra):
    return client.post(
        SIGNUP, {"email": email, "password": "S3cure-pass!word", **extra}, format="json"
    )


def test_signup_creates_user_workspace_owner_and_tokens():
    res = signup(APIClient(), "Ali@Example.com", name="Ali", workspace_name="Ali Traders")
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["email"] == "ali@example.com"
    assert body["workspaces"][0]["role"] == Role.OWNER
    assert body["access"] and body["refresh"]
    assert Membership.objects.filter(workspace__name="Ali Traders", role=Role.OWNER).count() == 1


def test_signup_rejects_duplicate_email_and_weak_password():
    c = APIClient()
    assert signup(c).status_code == 201
    assert signup(c, "A@example.com").status_code == 400
    weak = c.post(SIGNUP, {"email": "b@example.com", "password": "123"}, format="json")
    assert weak.status_code == 400


def test_login_then_me_with_jwt():
    c = APIClient()
    signup(c)
    tokens = c.post(
        "/api/v1/auth/login/",
        {"email": "a@example.com", "password": "S3cure-pass!word"},
        format="json",
    ).json()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    me = c.get("/api/v1/me/")
    assert me.status_code == 200 and me.json()["user"]["email"] == "a@example.com"
    refreshed = APIClient().post(
        "/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
    )
    assert refreshed.status_code == 200 and "access" in refreshed.json()


def test_login_wrong_password_and_anonymous_me():
    c = APIClient()
    signup(c)
    bad = c.post(
        "/api/v1/auth/login/", {"email": "a@example.com", "password": "nope"}, format="json"
    )
    assert bad.status_code == 401
    assert APIClient().get("/api/v1/me/").status_code == 401


def test_auth_endpoints_are_rate_limited():
    with override_settings(
        DOCSENSE_THROTTLE_RATES={"auth": "3/min", "user": "99/min", "apikey": "99/min"}
    ):
        c = APIClient()
        codes = [
            c.post(
                "/api/v1/auth/login/", {"email": "x@example.com", "password": "bad"}, format="json"
            ).status_code
            for _ in range(5)
        ]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]
