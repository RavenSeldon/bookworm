"""
Bookworm: Little Library Finder - App Configuration
"""

from django.apps import AppConfig


class LibrariesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'libraries'
    verbose_name = 'Little Free Libraries'

    def ready(self):
        # Import models to ensure signals are registered
        from . import models  # noqa: F401