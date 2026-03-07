"""
Bookworm: Little Library Finder — Sitemap Configuration

Generates sitemap.xml for search engine discovery.
All active, verified libraries are included with their canonical SEO URLs.

Setup:
    1. Add 'django.contrib.sitemaps' to INSTALLED_APPS
    2. Wire up in project urls.py
"""

from django.contrib.sitemaps import Sitemap
from .models import Library


class LibrarySitemap(Sitemap):
    """
    Sitemap for individual library detail pages.

    Uses get_absolute_url() from the Library model, which returns
    the PK-slug SEO URL (e.g. /library/42-oak-street-book-box/).
    """

    changefreq = 'weekly'
    protocol = 'https'

    def items(self):
        return Library.objects.filter(
            is_verified=True,
            is_active=True
        ).order_by('-last_updated')

    def lastmod(self, obj):
        return obj.last_updated

    def priority(self, obj):
        # Named libraries get higher priority
        if obj.name:
            return 0.7
        return 0.5

    def location(self, obj):
        return obj.get_absolute_url()


class StaticSitemap(Sitemap):
    """
    Sitemap for static pages (landing, map).
    """

    changefreq = 'daily'
    priority = 0.9
    protocol = 'https'

    def items(self):
        return ['/', '/map/']

    def location(self, item):
        return item