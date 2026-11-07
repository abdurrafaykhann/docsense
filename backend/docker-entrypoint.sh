#!/bin/sh
# Migrate, optionally seed the demo workspace (idempotent), then run the given command.
set -e
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi
if [ "${SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo
  [ -d /docs/eval-results ] && python manage.py import_eval   # idempotent
fi
exec "$@"
