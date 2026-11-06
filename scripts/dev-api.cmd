@echo off
rem Local demo API without Docker: SQLite + in-memory channels, seeded demo workspace.
rem   scripts\dev-api.cmd            (then: cd frontend && npm run dev)
set DJANGO_SETTINGS_MODULE=config.settings.dev
set CHANNEL_LAYER=memory
set CELERY_EAGER=1
set DATABASE_URL=sqlite:///%~dp0..\backend\demo.sqlite3
set MEDIA_ROOT=%~dp0..\backend\demo_media
cd /d %~dp0..\backend
.venv\Scripts\python manage.py migrate --noinput
.venv\Scripts\python manage.py seed_demo
.venv\Scripts\python manage.py runserver 8000 --noreload
