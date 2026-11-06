from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import usage
from .models import ApiKey, Membership, Role, Workspace
from .permissions import IsHumanUser, WorkspaceRolePermission

User = get_user_model()


def workspace_payload(ws: Workspace, role: str | None = None) -> dict:
    data = {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "daily_upload_limit": ws.daily_upload_limit,
        "max_upload_mb": ws.max_upload_mb,
    }
    if role:
        data["role"] = role
    return data


class WorkspaceListCreate(APIView):
    permission_classes = [IsHumanUser]

    def get(self, request):
        rows = Membership.objects.filter(user=request.user).select_related("workspace")
        return Response([workspace_payload(m.workspace, m.role) for m in rows])

    @transaction.atomic
    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "This field is required."})
        ws = Workspace.create_unique(name[:120])
        Membership.objects.create(user=request.user, workspace=ws, role=Role.OWNER)
        return Response(workspace_payload(ws, Role.OWNER), status=status.HTTP_201_CREATED)


class WorkspaceScoped(APIView):
    """Base for views under /workspaces/<workspace_id>/ ."""

    permission_classes = [IsAuthenticated, WorkspaceRolePermission]

    def workspace(self) -> Workspace:
        return get_object_or_404(Workspace, pk=self.kwargs["workspace_id"])


class WorkspaceDetail(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER if request.method == "PATCH" else Role.VIEWER

    def get(self, request, workspace_id):
        return Response(workspace_payload(self.workspace(), request.workspace_role))

    def patch(self, request, workspace_id):
        ws = self.workspace()
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "This field is required."})
        ws.name = name[:120]
        ws.save(update_fields=["name"])
        return Response(workspace_payload(ws, request.workspace_role))


class MemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices, default=Role.MEMBER)


def member_payload(m: Membership) -> dict:
    return {
        "id": m.id,
        "user_id": m.user_id,
        "email": m.user.email,
        "name": m.user.name,
        "role": m.role,
    }


def _owner_count(ws_id: int) -> int:
    return Membership.objects.filter(workspace_id=ws_id, role=Role.OWNER).count()


class MemberList(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER if request.method == "POST" else Role.VIEWER

    def get(self, request, workspace_id):
        rows = Membership.objects.filter(workspace_id=workspace_id).select_related("user")
        return Response([member_payload(m) for m in rows.order_by("id")])

    def post(self, request, workspace_id):
        ser = MemberSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.filter(email=ser.validated_data["email"].lower()).first()
        if user is None:
            raise ValidationError({"email": "No DocSense account with this email."})
        if Membership.objects.filter(user=user, workspace_id=workspace_id).exists():
            raise ValidationError({"email": "Already a member of this workspace."})
        m = Membership.objects.create(
            user=user, workspace_id=workspace_id, role=ser.validated_data["role"]
        )
        return Response(member_payload(m), status=status.HTTP_201_CREATED)


class MemberDetail(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER

    def _get(self, workspace_id, pk) -> Membership:
        return get_object_or_404(
            Membership.objects.select_related("user"), pk=pk, workspace_id=workspace_id
        )

    def patch(self, request, workspace_id, pk):
        m = self._get(workspace_id, pk)
        role = request.data.get("role")
        if role not in Role.values:
            raise ValidationError({"role": "Invalid role."})
        if m.role == Role.OWNER and role != Role.OWNER and _owner_count(workspace_id) <= 1:
            raise ValidationError({"role": "A workspace needs at least one owner."})
        m.role = role
        m.save(update_fields=["role"])
        return Response(member_payload(m))

    def delete(self, request, workspace_id, pk):
        m = self._get(workspace_id, pk)
        if m.role == Role.OWNER and _owner_count(workspace_id) <= 1:
            raise ValidationError({"detail": "A workspace needs at least one owner."})
        m.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def key_payload(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at,
        "last_used_at": k.last_used_at,
        "revoked": k.revoked_at is not None,
    }


class ApiKeyList(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER

    def get(self, request, workspace_id):
        keys = ApiKey.objects.filter(workspace_id=workspace_id).order_by("-id")
        return Response([key_payload(k) for k in keys])

    def post(self, request, workspace_id):
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "This field is required."})
        key, raw = ApiKey.issue(self.workspace(), name[:80], created_by=request.user)
        # The raw key is returned exactly once and never stored.
        return Response({**key_payload(key), "key": raw}, status=status.HTTP_201_CREATED)


class ApiKeyDetail(WorkspaceScoped):
    def required_role(self, request):
        return Role.OWNER

    def delete(self, request, workspace_id, pk):
        key = get_object_or_404(ApiKey, pk=pk, workspace_id=workspace_id)
        key.revoke()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsageView(WorkspaceScoped):
    def get(self, request, workspace_id):
        return Response(usage.usage_summary(self.workspace()))
