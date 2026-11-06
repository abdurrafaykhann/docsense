import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Role(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    MEMBER = "member", "Member"
    OWNER = "owner", "Owner"

    @property
    def rank(self) -> int:
        return {"viewer": 1, "member": 2, "owner": 3}[self.value]


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    daily_upload_limit = models.PositiveIntegerField(default=50)
    max_upload_mb = models.PositiveIntegerField(default=10)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def create_unique(cls, name: str, **extra) -> "Workspace":
        base = slugify(name)[:100] or "workspace"
        slug, n = base, 1
        while cls.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        return cls.objects.create(name=name, slug=slug, **extra)


class Membership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "workspace"], name="uniq_user_workspace")
        ]


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKey(models.Model):
    """Per-workspace machine credential. Only a SHA-256 hash is stored; raw key shown once."""

    PREFIX = "ds"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=12, unique=True, db_index=True)
    key_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @classmethod
    def issue(cls, workspace: Workspace, name: str, created_by=None) -> tuple["ApiKey", str]:
        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        raw = f"{cls.PREFIX}_{prefix}_{secret}"
        key = cls.objects.create(
            workspace=workspace,
            name=name,
            prefix=prefix,
            key_hash=hash_key(raw),
            created_by=created_by,
        )
        return key, raw

    def revoke(self) -> None:
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])


class UsageCounter(models.Model):
    """Daily per-workspace counters: uploads, upload_bytes, api_requests."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="usage")
    day = models.DateField()
    metric = models.CharField(max_length=40)
    count = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "day", "metric"], name="uniq_usage")
        ]
