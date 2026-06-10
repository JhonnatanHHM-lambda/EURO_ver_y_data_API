#!/bin/sh
set -e

if [ "${SKIP_MIGRATE:-false}" != "true" ]; then
    echo "Aplicando migraciones..."
    python manage.py migrate --noinput
    echo "Recolectando estáticos..."
    python manage.py collectstatic --noinput --clear 2>/dev/null || true
fi

echo "Iniciando..."
exec "$@"
