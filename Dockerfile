# =============================================================================
# Bookworm: Dockerfile for Railway
# =============================================================================
# Uses apt-get to install GDAL/GEOS/PROJ into standard Linux paths
# where Django's auto-detection works reliably.
# =============================================================================

FROM python:3.12-slim

# Install PostGIS/GDAL system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway sets PORT dynamically; env vars available at runtime only
CMD ["sh", "-c", "python manage.py migrate && python manage.py createcachetable 2>/dev/null; python manage.py collectstatic --noinput; exec gunicorn bookworm.wsgi --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120"]
