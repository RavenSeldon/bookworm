"""
Bookworm: Little Library Finder - Views

Views for map display, GeoJSON API, and form submissions.
Includes rate limiting for spam prevention.
Database-backed rate limiting that works across Gunicorn workers.
Includes user-friendly messages with countdown timers.
- Landing page view
- Geocoding endpoint for address search (Nominatim)
- N+1 query fix in GeoJSON endpoint
- Anti-bot timing checks
- Better error handling with retry support
- Form timestamp injection for bot detection
"""

import logging
from datetime import timedelta

import requests
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Count, Prefetch
from django.utils import timezone
from django.template.response import TemplateResponse
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache

from .models import Library, Shelfie, IssueReport
from .forms import LibrarySubmissionForm, ShelfieUploadForm, IssueReportForm
from .rate_limiting import rate_limit, check_submission_timing

logger = logging.getLogger(__name__)


# =============================================================================
# Landing Page
# =============================================================================

def landing_page(request):
    """
    Landing page with introduction and CTA to explore the map.
    Shows stats to build trust and excitement.
    """
    # Get stats for social proof
    stats = cache.get('landing_page_stats')
    if not stats:
        stats = {
            'library_count': Library.objects.filter(is_verified=True, is_active=True).count(),
            'shelfie_count': Shelfie.objects.count(),
            'recent_activity': Library.objects.filter(
                is_verified=True,
                is_active=True,
                last_updated__gte=timezone.now() - timedelta(days=7)
            ).count()
        }
        cache.set('landing_page_stats', stats, 300)

    return render(request, 'libraries/landing.html', {
        'page_title': 'Bookworm: Little Library Finder',
        **stats,
    })


# =============================================================================
# Main Map View
# =============================================================================

def map_view(request):
    """
    Main page with the interactive map.
    Library data is loaded asynchronously via GeoJSON API.
    """
    context = {
        'page_title': 'Bookworm: Little Library Finder',
        'default_lat': 49.2827,  # Vancouver, BC as default
        'default_lng': -123.1207,
        'default_zoom': 13,
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
    }
    return render(request, 'libraries/map.html', context)


# =============================================================================
# GeoJSON API
# =============================================================================

@require_GET
def libraries_geojson(request):
    """
    Serve verified, active libraries as GeoJSON for Leaflet.

    Uses annotate() to avoid N+1 query on shelfie_count.

    Query params:
        bbox: Bounding box as 'west,south,east,north'
        near_lat, near_lng, radius: Filter by proximity (km)
    """
    import hashlib

    # Build cache key from request parameters
    bbox = request.GET.get('bbox', '')
    near_lat = request.GET.get('near_lat', '')
    near_lng = request.GET.get('near_lng', '')
    radius = request.GET.get('radius', '10')

    # Round BBOX to 3 decimal places (~100m precision) to improve cache hits
    cache_bbox = ''
    if bbox:
        try:
            coords = [round(float(c), 3) for c in bbox.split(',')]
            cache_bbox = ','.join(map(str, coords))
        except (ValueError, TypeError):
            cache_bbox = bbox

    # Create cache key
    cache_key_data = f"geojson:{cache_bbox}:{near_lat}:{near_lng}:{radius}"
    cache_key = f"libraries_geojson_{hashlib.md5(cache_key_data.encode()).hexdigest()}"

    # Try to get from cache
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        response = JsonResponse(cached_response)
        response['X-Cache'] = 'HIT'
        return response

    # Build queryset
    libraries = Library.objects.filter(
        is_verified=True,
        is_active=True
    ).annotate(
        shelfie_count=Count('shelfies')
    ).prefetch_related('shelfies')

    # Optional: Filter by bounding box
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(','))
            bbox_poly = Polygon.from_bbox((west, south, east, north))
            libraries = libraries.filter(location__within=bbox_poly)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid bbox parameter: {bbox} - {e}")

    # Optional: Filter by proximity
    if near_lat and near_lng:
        try:
            point = Point(float(near_lng), float(near_lat), srid=4326)
            libraries = libraries.filter(
                location__distance_lte=(point, D(km=float(radius)))
            ).annotate(
                distance=Distance('location', point)
            ).order_by('distance')
        except (ValueError, TypeError):
            pass

    # Build GeoJSON
    features = []
    now = timezone.now()

    for library in libraries:
        # Calculate freshness
        age = now - library.last_updated
        if age < timedelta(days=7):
            freshness = 'fresh'
            color = '#22c55e'  # Green
        elif age < timedelta(days=21):
            freshness = 'stale'
            color = '#f59e0b'  # Amber
        else:
            freshness = 'needs_visit'
            color = '#78716c'  # Grey

        # Get latest shelfie using prefetched data
        shelfies = list(library.shelfies.all())
        latest_shelfie = shelfies[0] if shelfies else None

        shelfie_data = None
        if latest_shelfie:
            shelfie_data = {
                'photo_url': latest_shelfie.photo.url if latest_shelfie.photo else None,
                'book_highlights': latest_shelfie.book_highlights,
                'uploaded_at': latest_shelfie.uploaded_at.isoformat(),
            }

        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [library.location.x, library.location.y]
            },
            'properties': {
                'id': library.pk,
                'slug': library.slug or '',
                'name': library.name or f'Library #{library.pk}',
                'description': library.description,
                'freshness': freshness,
                'color': color,
                'last_updated': library.last_updated.isoformat(),
                'shelfie_count': library.shelfie_count,
                'latest_shelfie': shelfie_data,
            }
        }
        features.append(feature)

    geojson_data = {
        'type': 'FeatureCollection',
        'features': features
    }

    # Cache with configurable duration
    cache_duration = getattr(settings, 'GEOJSON_CACHE_DURATION', 60)
    cache.set(cache_key, geojson_data, cache_duration)

    response = JsonResponse(geojson_data)
    response['X-Cache'] = 'MISS'
    return response

# =============================================================================
# Geocoding API (Address Search)
# =============================================================================

@require_GET
@rate_limit('geocode_search', limit=30, period=60)
def geocode_address(request):
    """
    Geocode an address using Nominatim (OpenStreetMap).

    Usage: /api/geocode/?q=123+Main+St,+Vancouver

    Nominatim Usage Policy:
    - Max 1 request/second (enforced via rate limiting)
    - Must display attribution (handled in frontend)
    - No heavy usage
    """
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({'error': 'Please enter an address to search.'}, status=400)

    if len(query) < 3:
        return JsonResponse({'error': 'Please enter a more specific address.'}, status=400)

    try:
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': query,
                'format': 'json',
                'limit': 5,
                'addressdetails': 1,
            },
            headers={
                # Required by Nominatim ToS
                'User-Agent': 'Bookworm-LittleLibraryFinder/1.0',
            },
            timeout=5,
        )
        response.raise_for_status()

        results = response.json()

        if not results:
            return JsonResponse({
                'results': [],
                'message': "No results found. Try a different address or place a pin manually."
            })

        # Format results for frontend
        formatted = []
        for r in results:
            formatted.append({
                'display_name': r.get('display_name', ''),
                'lat': float(r.get('lat', 0)),
                'lon': float(r.get('lon', 0)),
                'type': r.get('type', ''),
                'importance': r.get('importance', 0),
            })

        logger.info(
            "Geocode search",
            extra={
                'query': query,
                'results_count': len(formatted),
                'ip': request.META.get('REMOTE_ADDR'),
            }
        )

        return JsonResponse({'results': formatted})

    except requests.Timeout:
        return JsonResponse({
            'error': 'Address search timed out. Please try again or place a pin manually.'
        }, status=504)

    except requests.RequestException as e:
        logger.error(f"Geocoding error: {e}")
        return JsonResponse({
            'error': 'Address search is temporarily unavailable. Please place a pin manually.'
        }, status=503)


# =============================================================================
# Library Detail (HTMX partial + full page with SEO URLs)
# =============================================================================

@require_GET
def library_detail(request, pk, slug=None):
    """
    Library detail view — serves both HTMX partials and full-page requests.

    SEO URL pattern: /library/<pk>-<slug>/
    If the slug in the URL doesn't match the library's current slug,
    redirect to the canonical URL (for non-HTMX requests).
    """
    library = get_object_or_404(
        Library.objects.prefetch_related(
            Prefetch('shelfies', queryset=Shelfie.objects.order_by('-uploaded_at'))
        ),
        pk=pk,
        is_verified=True,
        is_active=True
    )

    # For non-HTMX requests, enforce canonical URL
    if not request.headers.get('HX-Request') and slug and library.slug and slug != library.slug:
        return redirect(library.get_absolute_url(), permanent=True)

    context = {
        'library': library,
        'shelfies': library.shelfies.all()[:30],
        'shelfie_form': ShelfieUploadForm(library=library),
        'issue_form': IssueReportForm(library=library),
        'form_loaded_at': timezone.now().timestamp(),
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
    }

    # HTMX requests get partial, browser requests get the full page
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'libraries/partials/library_detail.html', context)

    # Full page for direct URL visits, social crawlers, etc.
    context['page_title'] = f"{library.name or 'Little Free Library'} — Bookworm"
    return TemplateResponse(request, 'libraries/library_detail_page.html', context)

@require_GET
def library_detail_bare(request, pk):
    """
    Bare PK URL handler: /library/<pk>/

    -HTMX requests: serve content directly (URL doesn't matter for partials)
    -Browser requests: redirect to canonical SEO URL if library has a slug
    """
    library = get_object_or_404(
        Library.objects.prefetch_related(
            Prefetch('shelfies', queryset=Shelfie.objects.order_by('-uploaded_at'))
        ),
        pk=pk,
        is_verified=True,
        is_active=True
    )

    # HTMX requests bypass redirect - just serve the partial
    if request.headers.get('HX-Request'):
            context = {
                'library': library,
                'shelfies': library.shelfies.all()[:30],
                'shelfie_form': ShelfieUploadForm(library=library),
                'issue_form': IssueReportForm(library=library),
                'form_loaded_at': timezone.now().timestamp(),
                'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
            }
            return TemplateResponse(request, 'libraries/partials/library_detail.html', context)

    # Browser request — redirect to canonical URL if library has a slug
    if library.slug:
        return redirect(library.get_absolute_url(), permanent=True)

    # No slug (unnamed library) — serve full page at this URL
    context = {
        'library': library,
        'shelfies': library.shelfies.all()[:30],
        'shelfie_form': ShelfieUploadForm(library=library),
        'issue_form': IssueReportForm(library=library),
        'form_loaded_at': timezone.now().timestamp(),
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
        'page_title': f"Library #{library.pk} — Bookworm",
    }
    return TemplateResponse(request, 'libraries/library_detail_page.html', context)


# =============================================================================
# Library Submission
# =============================================================================

@require_GET
def submit_library_form(request):
    """
    Display the library submission form (no rate limiting).
    """
    form = LibrarySubmissionForm()
    template = 'libraries/partials/submit_form.html'
    if not request.headers.get('HX-Request'):
        template = 'libraries/submit_library.html'
    return TemplateResponse(request, template, {
        'form': form,
        'form_loaded_at': timezone.now().timestamp(),  # For bot detection
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
    })

@require_POST
@rate_limit('library_submit', limit=10, period=3600)
def submit_library(request):
    """
    Handle library submission (rate_limited).
    """
    is_suspicious, timing_message = check_submission_timing(request)
    if is_suspicious:
        if request.headers.get('HX-Request'):
            return TemplateResponse(
                request,
                'libraries/partials/form_error.html',
                {'error': timing_message, 'retry_allowed': True},
                status=400
            )
        return JsonResponse({'error': timing_message}, status=400)

    form = LibrarySubmissionForm(request.POST, request.FILES)

    if form.is_valid():
        # Check honeypot
        if form.cleaned_data.get('website_url'):
            return JsonResponse({'error': 'Invalid submission'}, status=400)

        try:
            # Save library
            library = form.save()

            # Create initial Shelfie
            Shelfie.objects.create(
                library=library,
                photo=form.cleaned_data['photo'],
                book_highlights=form.cleaned_data.get('book_highlights', '')
            )

            logger.info(
                "Library submitted",
                extra={
                    'library_id': library.pk,
                    'has_name': bool(library.name),
                    'has_photo': True,
                    'ip': request.META.get('REMOTE_ADDR'),
                }
            )

            if getattr(settings, 'ADMIN_EMAIL', ''):
                library_url = request.build_absolute_uri(library.get_absolute_url())
                send_mail(
                    subject=f'[Bookworm] New library submitted: {library.name or f"Library #{library.pk}"}',
                    message=(
                        f'A new library has been submitted and is pending verification.\n\n'
                        f'Name: {library.name or "(unnamed)"}\n'
                        f'Location: {library.location.y:.5f}, {library.location.x:.5f}\n'
                        f'Submitted from IP: {request.META.get("REMOTE_ADDR", "unknown")}\n\n'
                        f'Review in admin: {request.build_absolute_uri("/admin/libraries/library/" + str(library.pk) + "/change/")}\n'
                        f'Public URL (once verified): {library_url}\n'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[settings.ADMIN_EMAIL],
                    fail_silently=True,  # Never crash a user's submission over email
                )

            # Return success response
            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/submit_success.html',
                    {'library': library}
                )
            return redirect('libraries:map')

        except Exception as e:
            logger.error(f"Error saving library submission: {e}")
            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/form_error.html',
                    {
                        'error': "We couldn't save your submission. Please try again.",
                        'retry_allowed': True,
                    },
                    status=500
                )
            return JsonResponse({'error': 'Server error. Please try again.'}, status=500)

    # Form invalid - return with errors
    template = 'libraries/partials/submit_form.html'
    if not request.headers.get('HX-Request'):
        template = 'libraries/submit_library.html'
    return TemplateResponse(request, template, {
        'form': form,
        'form_loaded_at': timezone.now().timestamp(),
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
    }, status=400)


# =============================================================================
# Shelfie Upload
# =============================================================================

@require_POST
@rate_limit('shelfie_upload', limit=10, period=3600)
def upload_shelfie(request, library_pk):
    """
    Handle Shelfie uploads to existing libraries.

    Better error handling with retry support.
    """
    library = get_object_or_404(
        Library,
        pk=library_pk,
        is_verified=True,
        is_active=True
    )

    # Check for bot timing
    is_suspicious, timing_message = check_submission_timing(request)
    if is_suspicious:
        if request.headers.get('HX-Request'):
            return TemplateResponse(
                request,
                'libraries/partials/form_error.html',
                {'error': timing_message, 'library': library, 'retry_allowed': True},
                status=400
            )
        return JsonResponse({'error': timing_message}, status=400)

    form = ShelfieUploadForm(request.POST, request.FILES, library=library)

    if form.is_valid():
        # Check honeypot
        if form.cleaned_data.get('website_url'):
            return JsonResponse({'error': 'Invalid submission'}, status=400)

        try:
            shelfie = form.save()

            logger.info(
                "Shelfie uploaded",
                extra={
                    'library_id': library.pk,
                    'shelfie_id': shelfie.pk,
                    'has_highlights': bool(shelfie.book_highlights),
                    'ip': request.META.get('REMOTE_ADDR'),
                }
            )

            if getattr(settings, 'ADMIN_EMAIL', ''):
                send_mail(
                    subject=f'[Bookworm] New shelfie uploaded: {library.name or f"Library #{library.pk}"}',
                    message=(
                        f'A new shelfie has been uploaded to a verified library.\n\n'
                        f'Library: {library.name or f"Library #{library.pk}"}\n'
                        f'Shelfie ID: {shelfie.pk}\n'
                        f'Highlights: {shelfie.book_highlights or "(none provided)"}\n'
                        f'Uploaded from IP: {request.META.get("REMOTE_ADDR", "unknown")}\n\n'
                        f'Review in admin: {request.build_absolute_uri("/admin/libraries/shelfie/" + str(shelfie.pk) + "/change/")}\n'
                        f'Library page: {request.build_absolute_uri(library.get_absolute_url())}\n'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[settings.ADMIN_EMAIL],
                    fail_silently=True,
                )

            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/shelfie_success.html',
                    {'library': library, 'shelfie': shelfie}
                )

            return JsonResponse({
                'success': True,
                'message': 'Shelfie uploaded successfully!',
                'shelfie_id': shelfie.pk
            })

        except Exception as e:
            logger.error(f"Error saving shelfie: {e}")
            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/form_error.html',
                    {
                        'error': "Upload failed. Please try again.",
                        'library': library,
                        'retry_allowed': True,
                    },
                    status=500
                )
            return JsonResponse({'error': 'Upload failed'}, status=500)

    # Form invalid
    if request.headers.get('HX-Request'):
        return TemplateResponse(
            request,
            'libraries/partials/shelfie_form.html',
            {
                'form': form,
                'library': library,
                'form_loaded_at': timezone.now().timestamp(),
                'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
            },
            status=400
        )

    return JsonResponse({
        'success': False,
        'errors': form.errors
    }, status=400)


# =============================================================================
# Issue Reporting
# =============================================================================

@require_POST
@rate_limit('issue_report', limit=5, period=3600)
def report_issue(request, library_pk):
    """Handle issue reports for a library."""
    library = get_object_or_404(Library, pk=library_pk)

    is_suspicious, timing_message = check_submission_timing(request)
    if is_suspicious:
        if request.headers.get('HX-Request'):
            return TemplateResponse(
                request,
                'libraries/partials/form_error.html',
                {'error': timing_message, 'library': library, 'retry_allowed': True},
                status=400
            )
        return JsonResponse({'error': timing_message}, status=400)

    form = IssueReportForm(request.POST, library=library)

    if form.is_valid():
        # Check honeypot
        if form.cleaned_data.get('website_url'):
            return JsonResponse({'error': 'Invalid submission'}, status=400)

        try:
            report = form.save()

            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/report_success.html',
                    {'library': library, 'report': report}
                )

            return JsonResponse({
                'success': True,
                'message': 'Issue reported. Thank you!'
            })

        except Exception as e:
            logger.error(f"Error saving issue report: {e}")
            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/form_error.html',
                    {'error': "Report submission failed. Please try again.", 'library': library},
                    status=500
                )
            return JsonResponse({'error': 'Submission failed'}, status=500)

    # Form invalid
    if request.headers.get('HX-Request'):
        return TemplateResponse(
            request,
            'libraries/partials/report_form.html',
            {'form': form, 'library': library},
            status=400
        )

    return JsonResponse({
        'success': False,
        'errors': form.errors
    }, status=400)


# =============================================================================
# Shelfie Photo Reporting
# =============================================================================

@require_GET
def shelfie_report_form_partial(request, shelfie_pk):
    """Return the shelfie report form as a partial (no rate limiting — read-only)."""
    shelfie = get_object_or_404(Shelfie, pk=shelfie_pk)
    library = shelfie.library
    form = IssueReportForm(library=library, shelfie=shelfie)
    return TemplateResponse(
        request,
        'libraries/partials/shelfie_report_form.html',
        {
            'form': form,
            'library': library,
            'shelfie': shelfie,
        }
    )

@require_POST
@rate_limit('issue_report', limit=5, period=3600)
def report_shelfie(request, shelfie_pk):
    """
    Handle reports for a specific shelfie photo (rate-limited).
    """
    shelfie = get_object_or_404(Shelfie, pk=shelfie_pk)
    library = shelfie.library

    form = IssueReportForm(request.POST, library=library, shelfie=shelfie)

    if form.is_valid():
        # Check honeypot
        if form.cleaned_data.get('website_url'):
            return JsonResponse({'error': 'Invalid submission'}, status=400)

        try:
            report = form.save()

            logger.info(
                "Shelfie reported",
                extra={
                    'library_id': library.pk,
                    'shelfie_id': shelfie.pk,
                    'issue_type': report.issue_type,
                    'ip': request.META.get('REMOTE_ADDR'),
                }
            )

            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/shelfie_report_success.html',
                    {'library': library, 'shelfie': shelfie, 'report': report}
                )

            return JsonResponse({
                'success': True,
                'message': 'Photo reported. Thank you!'
            })

        except Exception as e:
            logger.error(f"Error saving shelfie report: {e}")
            if request.headers.get('HX-Request'):
                return TemplateResponse(
                    request,
                    'libraries/partials/form_error.html',
                    {'error': "Report submission failed. Please try again.", 'library': library},
                    status=500
                )
            return JsonResponse({'error': 'Submission failed'}, status=500)

    # Form invalid
    if request.headers.get('HX-Request'):
        return TemplateResponse(
            request,
            'libraries/partials/shelfie_report_form.html',
            {'form': form, 'library': library, 'shelfie': shelfie},
            status=400
        )

    return JsonResponse({
        'success': False,
        'errors': form.errors
    }, status=400)

# =============================================================================
# Form Partials (HTMX)
# =============================================================================

@require_GET
def shelfie_form_partial(request, library_pk):
    """Return the Shelfie upload form as a partial."""
    library = get_object_or_404(Library, pk=library_pk, is_verified=True)
    form = ShelfieUploadForm(library=library)
    return TemplateResponse(
        request,
        'libraries/partials/shelfie_form.html',
        {
            'form': form,
            'library': library,
            'form_loaded_at': timezone.now().timestamp(),
            'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
        }
    )


@require_GET
def report_form_partial(request, library_pk):
    """Return the issue report form as a partial."""
    library = get_object_or_404(Library, pk=library_pk)
    form = IssueReportForm(library=library)
    return TemplateResponse(
        request,
        'libraries/partials/report_form.html',
        {
            'form': form,
            'library': library,
            'form_loaded_at': timezone.now().timestamp(),
        }
    )

# =============================================================================
# Sitemap Crawler
# =============================================================================

def robots_txt(request):
    """Serve robots.txt dynamically so the sitemap URL uses the correct domain."""
    sitemap_url = f"{request.scheme}://{request.get_host()}/sitemap.xml"
    content = f"""User-agent: *
Allow: /

Sitemap: {sitemap_url}"""
    return HttpResponse(content.strip(), content_type='text/plain')

# =============================================================================
# App Health Check
# =============================================================================

@require_GET
def health_check(request):
    return JsonResponse({'status': 'ok'})