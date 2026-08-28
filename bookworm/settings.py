"""
Django settings for Bookworm: Little Library Finder
Configured for local development (macOS/Conda) and Railway production.
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
import platform
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-key-for-local-development-only'
    else:
        raise ValueError("SECRET_KEY environment variable is required in production")


# =============================================================================
# SECURITY
# =============================================================================

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    h.strip()
    for h in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:8000,http://127.0.0.1:8000'
    ).split(',')
    if h.strip()
]

# =============================================================================
# INSTALLED APPS
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',

    # GeoDjango
    'django.contrib.gis',

    # Third-party
    'cloudinary_storage',
    'cloudinary',

    # Local apps
    'libraries',
]


# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'bookworm.middleware.SecurityHeadersMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# =============================================================================
# URL CONFIGURATION
# =============================================================================

ROOT_URLCONF = 'bookworm.urls'


# =============================================================================
# TEMPLATES
# =============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'libraries.context_processors.map_settings',
            ],
        },
    },
]


# =============================================================================
# WSGI
# =============================================================================

WSGI_APPLICATION = 'bookworm.wsgi.application'


# =============================================================================
# DATABASE (PostgreSQL + PostGIS)
# =============================================================================
# Railway provides DATABASE_URL; local dev uses individual DB_* vars.
# The engine override is critical — dj-database-url defaults to psycopg2,
# but GeoDjango requires the PostGIS backend.
# =============================================================================

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=60,
            conn_health_checks=True,
            engine='django.contrib.gis.db.backends.postgis',
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.postgis',
            'NAME': os.environ.get('DB_NAME', 'bookworm'),
            'USER': os.environ.get('DB_USER', os.environ.get('USER', 'postgres')),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
        }
    }


# =============================================================================
# PASSWORD VALIDATION
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Django 5.x STORAGES format (replaces deprecated STATICFILES_STORAGE)
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# =============================================================================
# BASEMAP TILES
# =============================================================================
# CARTO began requiring an API key for its raster (PNG) basemaps in Aug 2026;
# unkeyed requests are served with a repeating "API KEY REQUIRED" watermark.
# Keys are free, issued without an approval queue, 5M tile requests/month:
#   https://carto.com/basemaps/apikey/
#
# Every Leaflet map in the app reads TILE_URL from here, via the
# libraries.context_processors.map_settings context processor. Changing the
# basemap is one edit in this file, not a hunt through templates.
#
# NOTE: CARTO is retiring raster basemaps in favour of vector tiles, which
# would mean MapLibre GL rather than Leaflet. Deferred; see project notes.
# =============================================================================

CARTO_KEY = os.environ.get('CARTO_KEY', '')

TILE_URL = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'
if CARTO_KEY:
    TILE_URL += '?key=' + CARTO_KEY

TILE_SUBDOMAINS = 'abcd'
TILE_MAX_ZOOM = 19
TILE_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
)


# =============================================================================
# MEDIA FILES (Cloudinary)
# =============================================================================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cloudinary configuration
# django-cloudinary-storage reads CLOUDINARY_URL automatically when
# CLOUDINARY_STORAGE values are empty. We explicitly configure cloudinary
# from the URL to ensure both the base library and django-cloudinary-storage
# are properly initialized.
import cloudinary

CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')
if CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)


# =============================================================================
# CACHING (for rate limiting)
# =============================================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'bookworm_cache_table',
        'TIMEOUT': 3600,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 3,
        }
    }
}


# =============================================================================
# FILE UPLOADS
# =============================================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB


# =============================================================================
# DEFAULT PRIMARY KEY
# =============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# GDAL/GEOS LIBRARY PATHS (macOS with Homebrew)
# =============================================================================

if platform.system() == 'Darwin':  # macOS (Homebrew)
    GDAL_LIBRARY_PATH = '/opt/homebrew/opt/gdal/lib/libgdal.dylib'
    GEOS_LIBRARY_PATH = '/opt/homebrew/opt/geos/lib/libgeos_c.dylib'
else:
    # Linux (Docker/Railway) — apt-get installs to standard paths,
    # Django auto-detects. Env var override available as fallback.
    if os.environ.get('GDAL_LIBRARY_PATH'):
        GDAL_LIBRARY_PATH = os.environ['GDAL_LIBRARY_PATH']
    if os.environ.get('GEOS_LIBRARY_PATH'):
        GEOS_LIBRARY_PATH = os.environ['GEOS_LIBRARY_PATH']


# =============================================================================
# LOGGING
# =============================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        # Human-readable format for development
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },

        # JSON format for production
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(module)s %(message)s',
        },
    },
    'handlers': {
        # Console handler - uses verbose format in DEBUG, JSON in production
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if DEBUG else 'json',
        },
    },
    'loggers': {
        # Bookworm app logger
        'libraries': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },

        # Django request logger
        'django.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },

        # Security logger (login attempts, etc.)
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    # Root logger
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# =============================================================================
# CACHING CONFIGURATION
# =============================================================================

# GeoJSON response cache duration (seconds)
# - Development: 60 (1 minute)
# - Production: 120-180 (2-3 minutes)
GEOJSON_CACHE_DURATION = int(os.environ.get('GEOJSON_CACHE_DURATION', 120))

# =============================================================================
# RATE LIMITING CONFIGURATION
# =============================================================================

# Per-key 'escalates' flag:
#   - Default True (omitted): repeat offenders get progressively longer
#     timeouts via RATE_LIMIT_ESCALATION_TIERS. Right answer for write
#     endpoints (library_submit, shelfie_upload, etc).
#   - Set False for high-burst endpoints where a single user legitimately
#     hits the limit during normal use — escalation here would lock honest
#     users out of their stickers during the Library Hunt.
RATE_LIMIT_SETTINGS = {
    'library_submit':      {'limit': 50, 'period': 600},                       # 50 per 10 min
    'shelfie_upload':      {'limit': 50, 'period': 1800},                      # 50 per 30 min
    'issue_report':        {'limit': 10, 'period': 3600},                      # 10 per hour
    'geocode_search':      {'limit': 30, 'period': 60},                        # 30 per minute
    'steward_partnership': {'limit': 5,  'period': 3600},                      # 5 per hour
    'library_walk_register': {'limit': 10, 'period': 3600},                    # 10 per hour
    'here_resolve':        {'limit': 20, 'period': 300, 'escalates': False},   # 20 per 5 min
    'here_log':            {'limit': 20, 'period': 300, 'escalates': False},   # 20 per 5 min
}

# Progressive rate-limit escalation:
#   tier 1 = 1× base period (first offense)
#   tier 2 = 3×
#   tier 3 = 6×
#   tier 4+ = cap at 6×
# So library_submit (period=600s) escalates 10min → 30min → 60min → 60min.
# Read at runtime by libraries.rate_limiting; safe to tune without restart.
RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]

# How long an offender's tier persists after their last offense. After this
# many seconds with no further blocks, their next offense resets to tier 1.
RATE_LIMIT_OFFENSE_WINDOW_S = 86400  # 24 hours

# Anti-bot timing (minimum seconds before form can be submitted)
MIN_SUBMISSION_TIME_SECONDS = 2

# Upload validation (for client-side checks)
MAX_UPLOAD_SIZE_MB = 10

# =============================================================================
# DUPLICATE FLAGGING (Phase 3)
# =============================================================================
# When a new library is submitted, flag it for admin review if any active
# library already exists within this radius. Never blocks the submission.
# 20m comfortably distinguishes adjacent residential LFLs (typically >50m
# apart) from honest self-resubmits, while staying inside typical browser
# geolocation accuracy (10–50m).
DUPLICATE_PROXIMITY_RADIUS_M = 20

# Cap candidates per submission. Apartment-complex courtyards can have
# 3+ existing libraries within radius; admin only needs the closest few.
DUPLICATE_CANDIDATE_MAX = 3

# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# HTTPS settings (enable in production)
if os.environ.get('ENABLE_HTTPS', 'false').lower() == 'true':
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# HSTS (HTTP Strict Transport Security) - enable after confirming HTTPS works
# SECURE_HSTS_SECONDS = 31536000  # 1 year
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# =============================================================================
# EMAIL
# =============================================================================

def env_bool(name, default=False):
    return os.environ.get(str(name), str(default)).lower() in ("true", "1", "yes", "on")


RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if RESEND_API_KEY else "django.core.mail.backends.console.EmailBackend",
)

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.resend.com" if RESEND_API_KEY else "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "465"))

EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)

EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "resend")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", RESEND_API_KEY)

EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "15"))

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Bookworm <ben@bookworm.guide>",
)
SERVER_EMAIL = os.environ.get(
    "SERVER_EMAIL",
    "Bookworm <ben@bookworm.guide>",
)
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "ben.amuwo@gmail.com")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "ben.amuwo@gmail.com")