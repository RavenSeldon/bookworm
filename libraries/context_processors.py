"""
Template context processors for the libraries app.
"""

from django.conf import settings


def map_settings(request):
    """
    Expose the basemap tile configuration to every template.

    Single source of truth lives in settings.BASEMAP TILES. Templates should
    never hardcode a tile URL — swapping providers (or adding an API key)
    is then one edit in settings.py.
    """
    return {
        'TILE_URL': settings.TILE_URL,
        'TILE_ATTRIBUTION': settings.TILE_ATTRIBUTION,
        'TILE_SUBDOMAINS': settings.TILE_SUBDOMAINS,
        'TILE_MAX_ZOOM': settings.TILE_MAX_ZOOM,
    }
