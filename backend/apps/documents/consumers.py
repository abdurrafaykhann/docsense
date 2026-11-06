"""WebSocket: live pipeline progress for one document. Auth by JWT in ?token=."""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken

from apps.pipeline.progress import group_name, snapshot
from apps.workspaces.models import Membership

from .models import Document


@database_sync_to_async
def _authorize(token: str | None, document_id: int):
    if not token:
        return None
    try:
        user_id = AccessToken(token)["user_id"]
    except Exception:  # noqa: BLE001 - any invalid/expired token
        return None
    doc = Document.objects.filter(pk=document_id).first()
    if (
        doc is None
        or not Membership.objects.filter(user_id=user_id, workspace_id=doc.workspace_id).exists()
    ):
        return None
    return snapshot(doc)


class DocumentProgressConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        token = parse_qs(self.scope["query_string"].decode()).get("token", [None])[0]
        doc_id = int(self.scope["url_route"]["kwargs"]["document_id"])
        snap = await _authorize(token, doc_id)
        if snap is None:
            await self.close(code=4403)
            return
        self.group = group_name(doc_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"type": "snapshot", **snap})

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def progress(self, event):
        await self.send_json({"type": "progress", **event["payload"]})
