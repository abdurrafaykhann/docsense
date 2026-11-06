"""Rate limits with rates read from settings at request time (so tests can override them)."""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

from apps.workspaces.models import ApiKey


class _Base(SimpleRateThrottle):
    def get_rate(self):
        return settings.DOCSENSE_THROTTLE_RATES[self.scope]


class AuthRateThrottle(_Base):
    """Per-IP limit on signup/login to slow credential stuffing."""

    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class UserRateThrottle(_Base):
    scope = "user"

    def get_cache_key(self, request, view):
        if isinstance(request.auth, ApiKey) or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class ApiKeyRateThrottle(_Base):
    scope = "apikey"

    def get_cache_key(self, request, view):
        if not isinstance(request.auth, ApiKey):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.auth.pk}
