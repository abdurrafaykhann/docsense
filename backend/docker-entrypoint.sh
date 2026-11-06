#!/bin/sh
# Migrate, optionally seed the demo workspace (idempotent), then run the given command.
set -e
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi
if [ "${SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo
fi
exec "$@"
