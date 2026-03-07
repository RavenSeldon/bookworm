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
# MEDIA FILES (Cloudinary)
# =============================================================================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cloudinary configuration
CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY', ''),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET', ''),
}


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

if platform.system() == 'Darwin':  # macOS
    GDAL_LIBRARY_PATH = '/opt/homebrew/opt/gdal/lib/libgdal.dylib'
    GEOS_LIBRARY_PATH = '/opt/homebrew/opt/geos/lib/libgeos_c.dylib'


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

RATE_LIMIT_SETTINGS = {
    'library_submit': {'limit': 5, 'period': 3600},      # 5 per hour
    'shelfie_upload': {'limit': 10, 'period': 3600},     # 10 per hour
    'issue_report': {'limit': 5, 'period': 3600},        # 5 per hour
    'geocode_search': {'limit': 30, 'period': 60},       # 30 per minute
}

# Anti-bot timing (minimum seconds before form can be submitted)
MIN_SUBMISSION_TIME_SECONDS = 2

# Upload validation (for client-side checks)
MAX_UPLOAD_SIZE_MB = 10

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
# EMAIL (Admin notifications)
# =============================================================================
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Bookworm <noreply@bookworm.app>')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
