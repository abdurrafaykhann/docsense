import pytest
from django.conf import settings

from apps.llm.client import build_default_client


@pytest.mark.django_db
def test_health_endpoint(client):
    res = client.get("/api/v1/health/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": True, "service": "docsense"}


def test_default_client_is_offline_fake_under_test_settings():
    assert settings.LLM_PROVIDER == "fake"
    assert build_default_client().providers[0].name == "fake"
