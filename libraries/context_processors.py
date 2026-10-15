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


def donation_settings(request):
    """
    Expose the donation links to every template, for the footers and the map
    navbar. BITCOIN_ADDRESS is '' unless libraries.donations has verified it,
    so templates can simply test it: an unproven address is never rendered.
    """
    from .donations import bitcoin_address

    return {
        'KOFI_URL': getattr(settings, 'KOFI_URL', ''),
        'BITCOIN_ADDRESS': bitcoin_address(),
    }
