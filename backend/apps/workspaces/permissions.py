from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .auth import ApiKeyPrincipal, role_for
from .models import Role


class IsHumanUser(BasePermission):
    """JWT/session users only; workspace API keys are rejected."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated) and not isinstance(
            request.user, ApiKeyPrincipal
        )


class WorkspaceRolePermission(BasePermission):
    """Requires `workspace_id` in the URL. Non-members get 404 (no existence leak).

    Views can define `required_role(request) -> Role`; default is viewer for reads,
    member for writes.
    """

    def has_permission(self, request, view):
        workspace_id = view.kwargs.get("workspace_id")
        role = role_for(request, workspace_id)
        if role is None:
            raise NotFound()
        request.workspace_role = role
        if hasattr(view, "required_role"):
            required = view.required_role(request)
        else:
            required = Role.VIEWER if request.method in SAFE_METHODS else Role.MEMBER
        return role.rank >= required.rank
