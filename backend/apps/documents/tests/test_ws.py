import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.files.base import ContentFile
from django.urls import path
from rest_framework_simplejwt.tokens import AccessToken

from apps.documents.consumers import DocumentProgressConsumer
from apps.documents.models import Document
from apps.pipeline.progress import initial_progress, publish

pytestmark = pytest.mark.django_db(transaction=True)

app = URLRouter([path("ws/documents/<int:document_id>/", DocumentProgressConsumer.as_asgi())])


@pytest.fixture
def doc(world):
    d = Document(
        workspace=world["ws"],
        original_name="a.png",
        content_type="image/png",
        size=1,
        sha256="x",
        progress=initial_progress(),
    )
    d.file.save("a.png", ContentFile(b"x"), save=True)
    return d


async def connect(doc_id, token):
    comm = WebsocketCommunicator(app, f"/ws/documents/{doc_id}/?token={token}")
    ok, _ = await comm.connect()
    return comm, ok


def test_member_receives_snapshot_then_live_progress(world, doc):
    token = str(AccessToken.for_user(world["users"]["viewer"]))

    async def scenario():
        comm, ok = await connect(doc.id, token)
        assert ok
        snap = await comm.receive_json_from()
        assert snap["type"] == "snapshot" and snap["steps"]["ocr"]["status"] == "pending"
        from asgiref.sync import sync_to_async

        await sync_to_async(publish)(doc, "ocr", "running", "page 1")
        msg = await comm.receive_json_from()
        assert (msg["type"], msg["step"], msg["status"]) == ("progress", "ocr", "running")
        await comm.disconnect()

    async_to_sync(scenario)()


def test_outsider_invalid_and_missing_token_rejected(world, doc):
    outsider = str(AccessToken.for_user(world["users"]["outsider"]))

    async def scenario():
        for tok in (outsider, "garbage", ""):
            _, ok = await connect(doc.id, tok)
            assert not ok

    async_to_sync(scenario)()
