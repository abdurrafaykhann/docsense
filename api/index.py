# ruff: noqa
"""Vercel entrypoint: serves the read-only DocSense demo API (Django, ASGI) as one serverless function.

Cold start: Vercel's filesystem is read-only except /tmp, so the pre-seeded SQLite file and the sample images are
copied there once per instance. Everything else (OCR, layout model, uploads, retraining) is switched off by
DEMO_READONLY; see backend/apps/common/middleware.py and the README for what the hosted demo leaves out.
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(os.environ.get("DEMO_TMP", "/tmp"))  # the only writable place on Vercel
TMP.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "backend"))

for key, value in {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_ALLOWED_HOSTS": ".vercel.app,localhost,127.0.0.1",
    "DEMO_READONLY": "1",
    "DEMO_ASK_DAILY_CAP": "150",
    "CELERY_EAGER": "1",
    "CHANNEL_LAYER": "memory",
    "EMBEDDER": "hash",
    "RERANKER": "overlap",
    "OCR_ENGINE": "fake",
    "SEED_DIR": str(ROOT / "seed" / "demo_workspace"),
    "MEDIA_ROOT": str(TMP / "media"),
    "DATABASE_URL": f"sqlite:///{(TMP / 'demo.db').as_posix()}",
}.items():
    os.environ.setdefault(key, value)

DB = TMP / "demo.db"
if not DB.exists():
    shutil.copyfile(ROOT / "deploy" / "demo.db", DB)

from django.core.management import call_command  # noqa: E402

import django  # noqa: E402

django.setup()
call_command("restore_demo_media", verbosity=0)  # idempotent: writes the sample images under MEDIA_ROOT

from config.asgi import application as app  # noqa: E402,F401
