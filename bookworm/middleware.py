"""
Bookworm: Security Middleware
=============================
Adds security headers to all responses.
"""

from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to all responses.

    Headers added:
    - Content-Security-Policy (CSP)
    - X-Frame-Options
    - X-Content-Type-Options
    - Referrer-Policy
    - Permissions-Policy
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip CSP for admin (can cause issues with admin widgets)
        is_admin = request.path.startswith('/admin/')

        # Content-Security-Policy
        if not is_admin and not response.has_header('Content-Security-Policy'):
            csp = self.build_csp()
            response['Content-Security-Policy'] = csp

        # X-Frame-Options - Prevent clickjacking
        if not response.has_header('X-Frame-Options'):
            response['X-Frame-Options'] = 'DENY'

        # X-Content-Type-Options - Prevent MIME sniffing
        if not response.has_header('X-Content-Type-Options'):
            response['X-Content-Type-Options'] = 'nosniff'

        # Referrer-Policy - Control referrer information
        if not response.has_header('Referrer-Policy'):
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions-Policy - Restrict browser features
        if not response.has_header('Permissions-Policy'):
            response['Permissions-Policy'] = 'geolocation=(self), camera=(self), microphone=()'

        return response

    def build_csp(self):
        """
        Build Content-Security-Policy header value.

        Configured for Bookworm's specific needs:
        - CDNs: Bootstrap, HTMX, Leaflet, Google Fonts
        - Images: Cloudinary, OpenStreetMap tiles
        - APIs: Nominatim geocoding
        """

        # Cloudinary delivery host. Pinned to the exact host and scheme rather
        # than a '*.cloudinary.com' wildcard: it is narrower, and it makes the
        # required scheme explicit. (A schemeless source matches https only on
        # an https page, which is the second reason the old http:// shelfie
        # URLs were blocked in in-app browsers.)
        cloudinary_domain = 'https://res.cloudinary.com'

        directives = {
            # Default fallback
            'default-src': ["'self'"],

            # Scripts: CDNs + inline (required for current map.html)
            'script-src': [
                "'self'",
                "'unsafe-inline'",  # Required for inline scripts in map.html
                "https://cdn.jsdelivr.net",  # Bootstrap
                "https://unpkg.com",  # HTMX, Leaflet
            ],

            # Styles: CDNs + inline (required for inline styles)
            'style-src': [
                "'self'",
                "'unsafe-inline'",  # Required for inline styles
                "https://cdn.jsdelivr.net",  # Bootstrap
                "https://fonts.googleapis.com",  # Google Fonts
                "https://unpkg.com",  # Leaflet
            ],

            # Fonts
            'font-src': [
                "'self'",
                "https://fonts.gstatic.com",  # Google Fonts
                "https://cdn.jsdelivr.net",  # Bootstrap Icons
            ],

            # Images
            'img-src': [
                "'self'",
                "data:",  # Image previews, inline images
                "blob:",  # File uploads
                cloudinary_domain,  # Cloudinary images
                "https://*.tile.openstreetmap.org",  # OSM tiles
                "https://*.basemaps.cartocdn.com",  # CartoDB tiles
            ],

            # API connections
            'connect-src': [
                "'self'",
                "https://nominatim.openstreetmap.org",  # Geocoding
                "https://cdn.jsdelivr.net",  # Bootstrap source maps
                "https://unpkg.com",  # Leaflet source maps
            ],

            # Forms can only submit to self
            'form-action': ["'self'"],

            # Prevent embedding in frames
            'frame-ancestors': ["'none'"],

            # Base URI
            'base-uri': ["'self'"],
        }

        # Build CSP string
        csp_parts = []
        for directive, sources in directives.items():
            csp_parts.append(f"{directive} {' '.join(sources)}")

        # Valueless directive, appended separately: it takes no source list, so
        # putting it in the dict above would emit a stray trailing space.
        #
        # Rewrites http:// subresource requests to https:// *before* the
        # mixed-content check runs. Unlike Chrome's automatic upgrade, this is
        # honoured by WebKit and Android WebView, so it protects the in-app
        # browsers (Instagram, Facebook) that otherwise block mixed content
        # outright and silently. Defence in depth behind cloudinary's
        # secure=True: it also covers anything Django does not generate --
        # embeds, third-party assets, hand-written URLs, old pasted links.
        csp_parts.append('upgrade-insecure-requests')

        return '; '.join(csp_parts)
