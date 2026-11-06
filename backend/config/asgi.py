import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.urls import path  # noqa: E402

from apps.documents.consumers import DocumentProgressConsumer  # noqa: E402

websocket_urlpatterns = [
    path("ws/documents/<int:document_id>/", DocumentProgressConsumer.as_asgi()),
]

application = ProtocolTypeRouter(
    {"http": django_asgi_app, "websocket": URLRouter(websocket_urlpatterns)}
)
