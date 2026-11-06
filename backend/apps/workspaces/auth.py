"""X-API-Key authentication and role resolution."""

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from . import usage
from .models import ApiKey, Membership, Role, hash_key


class ApiKeyPrincipal:
    """Stand-in for request.user when a request is authenticated by workspace API key."""

    is_authenticated = True
    is_anonymous = False
    is_staff = False

    def __init__(self, key: ApiKey):
        self.key = key
        self.pk = f"apikey:{key.pk}"
        self.workspace_id = key.workspace_id

    def __str__(self) -> str:
        return f"ApiKey({self.key.prefix})"


class ApiKeyAuthentication(BaseAuthentication):
    header = "HTTP_X_API_KEY"

    def authenticate(self, request):
        raw = request.META.get(self.header)
        if not raw:
            return None
        parts = raw.split("_", 2)
        if len(parts) != 3 or parts[0] != ApiKey.PREFIX:
            raise AuthenticationFailed("Invalid API key.")
        key = ApiKey.objects.select_related("workspace").filter(prefix=parts[1]).first()
        if key is None or not key.is_active or key.key_hash != hash_key(raw):
            raise AuthenticationFailed("Invalid API key.")
        key.last_used_at = timezone.now()
        key.save(update_fields=["last_used_at"])
        usage.bump(key.workspace_id, usage.API_REQUESTS)
        return ApiKeyPrincipal(key), key

    def authenticate_header(self, request):
        return "X-API-Key"


def role_for(request, workspace_id: int) -> Role | None:
    """Effective role of the caller in a workspace, or None if they have no access."""
    if isinstance(request.auth, ApiKey):
        # API keys act as `member` in exactly one workspace.
        return Role.MEMBER if request.auth.workspace_id == workspace_id else None
    m = Membership.objects.filter(user=request.user, workspace_id=workspace_id).first()
    return Role(m.role) if m else None
