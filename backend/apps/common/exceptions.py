"""DRF exception handler: a missing LLM key is a configuration problem, not a server crash."""

from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        text = str(exc).lower()
        if "api_key" in text or "api key" in text:
            return Response(
                {
                    "detail": (
                        "The language model is not configured on this server (no API key). "
                        "Set GOOGLE_API_KEY and/or GROQ_API_KEY."
                    )
                },
                status=503,
            )
    return response
