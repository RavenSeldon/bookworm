release: python manage.py migrate && python manage.py createcachetable && python manage.py collectstatic --noinput
web: gunicorn bookworm.wsgi --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120
