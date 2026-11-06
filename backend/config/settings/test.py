from .base import *  # noqa: F403
from .base import BASE_DIR

SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256-signing"
LLM_PROVIDER = "fake"
CELERY_TASK_ALWAYS_EAGER = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DOCSENSE_THROTTLE_RATES = {"auth": "1000/min", "user": "1000/min", "apikey": "1000/min"}
OCR_ENGINE = "fake"
MEDIA_ROOT = BASE_DIR / "test_media"
LAYOUT_MODEL_PATH = ""
EMBEDDER = "hash"
RERANKER = "overlap"
