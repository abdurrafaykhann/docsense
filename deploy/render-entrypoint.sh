#!/bin/sh
# Migrate (idempotent), restore the demo images onto the ephemeral disk, serve on Render's $PORT.
set -e
python manage.py migrate --noinput
python manage.py restore_demo_media
exec daphne -b 0.0.0.0 -p "${PORT:-10000}" config.asgi:application
