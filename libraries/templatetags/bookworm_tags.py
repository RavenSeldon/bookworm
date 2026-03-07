"""
Bookworm: Little Library Finder — Custom Template Tags

Provides:
- cloudinary_og_image: Transforms a Cloudinary URL for Open Graph sharing (1200×630)
"""

import re
from django import template

register = template.Library()


@register.filter
def cloudinary_og_image(photo_url):
    """
    Transform a Cloudinary image URL into a social-sharing optimized version.

    Inserts Cloudinary transformations for a 1200×630 center-cropped image
    (the recommended Open Graph image size) with auto quality and format.

    Usage in templates:
        {{ shelfie.photo.url|cloudinary_og_image }}

    Input:  https://res.cloudinary.com/xxx/image/upload/v123/bookworm/shelfies/abc.jpg
    Output: https://res.cloudinary.com/xxx/image/upload/c_fill,w_1200,h_630,g_center,q_auto,f_auto/v123/bookworm/shelfies/abc.jpg
    """
    if not photo_url:
        return ''

    url = str(photo_url)

    # Match Cloudinary upload URLs and insert transformations after /upload/
    # Handles both with and without existing transformations
    transformed = re.sub(
        r'(/upload/)',
        r'\1c_fill,w_1200,h_630,g_center,q_auto,f_auto/',
        url,
        count=1
    )

    return transformed