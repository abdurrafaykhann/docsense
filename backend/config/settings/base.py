import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "channels",
    "apps.common",
    "apps.accounts",
    "apps.workspaces",
    "apps.llm",
    "apps.documents",
    "apps.pipeline",
    "apps.evaluation",
    "apps.learning",
    "apps.rag",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"), conn_max_age=60
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.workspaces.auth.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.common.throttles.UserRateThrottle",
        "apps.common.throttles.ApiKeyRateThrottle",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

# --- Redis / Celery / Channels -------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env("CELERY_EAGER", "0") == "1"
CELERY_TASK_TRACK_STARTED = True

if env("CHANNEL_LAYER", "redis") == "memory":
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }

# --- LLM (free tier) ------------------------------------------------------
LLM_PROVIDER = env("LLM_PROVIDER", "groq")  # groq | gemini | fake
LLM_PRIMARY = {"provider": "groq", "model": env("GROQ_MODEL", "llama-3.3-70b-versatile")}
LLM_FALLBACK = {"provider": "google_genai", "model": env("GEMINI_MODEL", "gemini-2.0-flash")}
LLM_MAX_RETRIES = int(env("LLM_MAX_RETRIES", "3"))
LLM_MAX_WAIT_SECONDS = float(env("LLM_MAX_WAIT_SECONDS", "30"))

# --- Auth / rate limiting ---------------------------------------------------
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}
DOCSENSE_THROTTLE_RATES = {"auth": "20/min", "user": "300/min", "apikey": "120/min"}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
if env("CACHE_REDIS", "0") == "1":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

# --- Documents / pipeline ---------------------------------------------------
OCR_ENGINE = env("OCR_ENGINE", "doctr")  # doctr | fake
ALLOWED_UPLOAD_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MAX_PAGES_PER_DOC = int(env("MAX_PAGES_PER_DOC", "6"))
LLM_MAX_PROMPT_CHARS = int(env("LLM_MAX_PROMPT_CHARS", "12000"))
LAYOUT_MODEL_PATH = env(
    "LAYOUT_MODEL_PATH", str(BASE_DIR.parent / "ml" / "models" / "layout-current.pt")
)

# --- RAG ----------------------------------------------------------------------
EMBEDDER = env("EMBEDDER", "st")  # st = local sentence-transformers | hash = offline test embedder
RERANKER = env("RERANKER", "ce")  # ce = local cross-encoder | overlap = offline test reranker
