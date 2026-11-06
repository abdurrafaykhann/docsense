from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.throttles import AuthRateThrottle
from apps.workspaces.models import Membership, Role, Workspace
from apps.workspaces.permissions import IsHumanUser

User = get_user_model()


def memberships_payload(user) -> list[dict]:
    rows = Membership.objects.filter(user=user).select_related("workspace").order_by("id")
    return [
        {
            "workspace_id": m.workspace_id,
            "name": m.workspace.name,
            "slug": m.workspace.slug,
            "role": m.role,
        }
        for m in rows
    ]


def user_payload(user) -> dict:
    return {"id": user.pk, "email": user.email, "name": user.name, "is_staff": user.is_staff}


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    workspace_name = serializers.CharField(required=False, allow_blank=True, max_length=120)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"])
        return attrs


class SignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [AuthRateThrottle]

    @transaction.atomic
    def post(self, request):
        ser = SignupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = User.objects.create_user(d["email"], d["password"], name=d.get("name", ""))
        ws_name = (
            d.get("workspace_name") or f"{d.get('name') or d['email'].split('@')[0]}'s workspace"
        )
        ws = Workspace.create_unique(ws_name)
        Membership.objects.create(user=user, workspace=ws, role=Role.OWNER)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": user_payload(user),
                "workspaces": memberships_payload(user),
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    throttle_classes = [AuthRateThrottle]


class RefreshView(TokenRefreshView):
    throttle_classes = [AuthRateThrottle]


class MeView(APIView):
    permission_classes = [IsHumanUser]

    def get(self, request):
        return Response(
            {"user": user_payload(request.user), "workspaces": memberships_payload(request.user)}
        )
