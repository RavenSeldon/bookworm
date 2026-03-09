#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate

echo "Creating cache table..."
python manage.py createcachetable 2>/dev/null || true

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Ensuring superuser exists..."
python manage.py createsuperuser --noinput 2>/dev/null || true

echo "Starting Gunicorn on port ${PORT}..."
exec gunicorn bookworm.wsgi --bind "0.0.0.0:${PORT}" --workers 2 --threads 2 --timeout 120
