#!/bin/bash
set -e

echo "Applying database migrations..."
python manage.py migrate

echo "Seeding database (skipped if data already exists)..."
python manage.py seed_all_if_empty

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
