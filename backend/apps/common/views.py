from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness + DB check used by docker-compose and the frontend shell."""
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        db_ok = cur.fetchone()[0] == 1
    return Response({"status": "ok" if db_ok else "degraded", "db": db_ok, "service": "docsense"})
