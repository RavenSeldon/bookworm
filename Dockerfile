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
