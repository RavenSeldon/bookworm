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
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.urls import reverse
from django.db.models import Count, Prefetch
from django.utils import timezone
from django.template.response import TemplateResponse
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache

from .models import Library, Shelfie, IssueReport, StewardPartnership, ScanEvent, DuplicateCandidate
from .forms import LibrarySubmissionForm, ShelfieUploadForm, IssueReportForm, StewardPartnershipForm
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
    Display the library submission form.

    HTMX requests get the form partial (loaded into the map's offcanvas).
    Direct browser visits to /submit/ get redirected to the map with
    ?submit=1, which the map's init script reads to auto-open the
    submit offcanvas. There is no standalone full-page submit template —
    submission requires the embedded Leaflet location picker that lives
    in map.html.
    """
    if not request.headers.get('HX-Request'):
        return redirect(reverse('libraries:map') + '?submit=1')

    form = LibrarySubmissionForm()
    return TemplateResponse(request, 'libraries/partials/submit_form.html', {
        'form': form,
        'form_loaded_at': timezone.now().timestamp(),
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
    })

@require_POST
@rate_limit('library_submit', limit=50, period=600)
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

            # Flag potential spatial duplicates for admin review (never blocks).
            _flag_duplicates(library)

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
    if not request.headers.get('HX-Request'):
        # Non-HTMX POST that failed validation — bounce to the map.
        # The user will need to retry via the offcanvas.
        return redirect(reverse('libraries:map') + '?submit=1')
    return TemplateResponse(request, 'libraries/partials/submit_form.html', {
        'form': form,
        'form_loaded_at': timezone.now().timestamp(),
        'max_upload_size_mb': getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10),
    }, status=400)


# =============================================================================
# Shelfie Upload
# =============================================================================

@require_POST
@rate_limit('shelfie_upload', limit=50, period=1800)
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
@rate_limit('issue_report', limit=10, period=3600)
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
@rate_limit('issue_report', limit=10, period=3600)
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


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

# Picker thresholds — adjust based on real scan distance distributions after
# the first few weeks of stickers in the wild.
HERE_DIRECT_MATCH_RADIUS_M = 25  # nearest within 25m → likely the right one
HERE_PICKER_RADIUS_M = 100  # nothing past 100m is a plausible candidate
HERE_DISAMBIGUATION_GAP_M = 50  # gap between #1 and #2 to call it "clear"
HERE_PICKER_MAX_CANDIDATES = 3  # most candidates we'll show in the picker


def _round_coord(value: float, places: int = 4) -> float:
    """Round a coord to N decimal places. 4 ≈ 11m on the ground."""
    return round(value, places)


def _log_scan(
        outcome: str,
        *,
        matched=None,
        candidate_count: int = 0,
        user_point=None,
        accuracy=None,
):
    """
    Persist a ScanEvent with rounded coords. Never raises — analytics
    must not break the user flow.
    """
    try:
        rounded = None
        if user_point is not None:
            rounded = Point(
                _round_coord(user_point.x),
                _round_coord(user_point.y),
                srid=4326,
            )
        ScanEvent.objects.create(
            outcome=outcome,
            matched_library=matched,
            candidate_count=candidate_count,
            location=rounded,
            accuracy_meters=accuracy,
        )
    except Exception as exc:  # pragma: no cover — analytics must not crash views
        logger.warning(
            "scan_event_log_failed",
            extra={"outcome": outcome, "error": str(exc)},
        )


def _coerce_float(raw):
    """POST values come as strings; return float or None."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# Duplicate flagging (Phase 3)
# -----------------------------------------------------------------------------


def _flag_duplicates(library):
    """
    On submission, flag the new library if any active existing library lies
    within ``DUPLICATE_PROXIMITY_RADIUS_M``. Creates up to
    ``DUPLICATE_CANDIDATE_MAX`` ``DuplicateCandidate`` rows, closest first.

    Identity-agnostic by design — records the spatial relationship, not who
    submitted. Wrapped in try/except so submission flow never breaks if the
    spatial query fails for any reason. Never blocks the user.

    The candidate set includes unverified-but-active libraries: the most
    common duplicate scenario is a user submitting twice from the same
    form-load, and both rows are unverified at that point.
    """
    try:
        radius_m = getattr(settings, "DUPLICATE_PROXIMITY_RADIUS_M", 20)
        max_candidates = getattr(settings, "DUPLICATE_CANDIDATE_MAX", 3)

        nearby = list(
            Library.objects.filter(
                is_active=True,
                location__distance_lte=(library.location, D(m=radius_m)),
            )
            .exclude(pk=library.pk)
            .annotate(distance=Distance("location", library.location))
            .order_by("distance")[:max_candidates]
        )

        for candidate in nearby:
            DuplicateCandidate.objects.create(
                submitted_library=library,
                existing_library=candidate,
                distance_meters=int(round(candidate.distance.m)),
            )

        if nearby:
            logger.info(
                "library_duplicate_flagged",
                extra={
                    "library_id": library.pk,
                    "candidate_count": len(nearby),
                    "closest_pk": nearby[0].pk,
                    "closest_distance_m": int(round(nearby[0].distance.m)),
                },
            )
    except Exception as exc:  # pragma: no cover — must never break submit
        logger.warning(
            "duplicate_flagging_failed",
            extra={"library_id": library.pk, "error": str(exc)},
        )

# -----------------------------------------------------------------------------
# Partnership flow (traditional GET form / POST submit / GET thanks)
# -----------------------------------------------------------------------------


@require_GET
def partnership_form(request):
    """GET /partners/ — render the steward consent form (full page)."""
    form = StewardPartnershipForm()
    return render(
        request,
        "libraries/partnership_form.html",
        {
            "form": form,
            "form_loaded_at": timezone.now().timestamp(),
        },
    )


@require_POST
@rate_limit("steward_partnership", limit=5, period=3600)
def partnership_submit(request):
    """POST /partners/submit/ — process steward partnership submission."""
    is_too_fast, timing_message = check_submission_timing(request)
    if is_too_fast:
        # Re-render the form page with the error attached.
        form = StewardPartnershipForm(request.POST)
        form.add_error(None, timing_message)
        return render(
            request,
            "libraries/partnership_form.html",
            {
                "form": form,
                "form_loaded_at": timezone.now().timestamp(),
            },
            status=400,
        )

    form = StewardPartnershipForm(request.POST)

    # Belt-and-suspenders honeypot check (the mixin runs first, this catches
    # any bot that bypassed validation somehow).
    if request.POST.get("website_url"):
        logger.warning(
            "consent_honeypot_tripped",
            extra={"path": request.path},
        )
        return HttpResponseBadRequest("Invalid submission.")

    if not form.is_valid():
        return render(
            request,
            "libraries/partnership_form.html",
            {
                "form": form,
                "form_loaded_at": timezone.now().timestamp(),
            },
            status=422,
        )

    partnership = form.save()

    # Notify admin — fail silently to never break the steward's flow.
    admin_email = getattr(settings, "ADMIN_EMAIL", None)
    if admin_email:
        send_mail(
            subject=(
                f"[Bookworm] New steward partnership: "
                f"{partnership.library_address[:60]}"
            ),
            message=(
                f"A steward has submitted a partnership response.\n\n"
                f"Library: {partnership.library_address}\n"
                f"Name: {partnership.name or '(not provided)'}\n"
                f"Contact: {partnership.contact}\n"
                f"Sticker interest: {'Yes' if partnership.sticker_interest else 'No'}\n"
                f"Library Hunt interest: "
                f"{partnership.get_hunt_interest_display()}\n"
                f"Visitor message: {partnership.hunt_message or '(none)'}\n\n"
                f"Review and match to a library record in the admin:\n"
                f"https://bookworm.guide/admin/libraries/stewardpartnership/"
                f"{partnership.pk}/change/\n"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", admin_email),
            recipient_list=[admin_email],
            fail_silently=True,
        )

    logger.info(
        "steward_partnership_submitted",
        extra={
            "partnership_id": partnership.pk,
            "sticker": partnership.sticker_interest,
            "hunt": partnership.hunt_interest,
        },
    )

    return redirect("libraries:partnership_thanks")


@require_GET
def partnership_thanks(request):
    """GET /partners/thanks/ — post-submission thank-you page."""
    return render(request, "libraries/partnership_thanks.html", {})


# -----------------------------------------------------------------------------
# /here/ — QR sticker landing page + coord resolver
# -----------------------------------------------------------------------------


@require_GET
def here_landing(request):
    """
    GET /here/ — the QR sticker target.

    Renders a minimal full page with a 'Find my library' button. The button
    triggers JS-side geolocation (gesture required by modern browsers), then
    POSTs the coords to /here/resolve/ via HTMX.
    """
    return render(request, "libraries/here.html", {})


@require_POST
@rate_limit("here_resolve", limit=20, period=300)
def here_resolve(request):
    """
    POST /here/resolve/ — resolve a scan's coords to a library.

    Returns one of:
      - HX-Redirect header → browser navigates to library detail page
      - here_picker.html partial → user chooses among ambiguous candidates
      - here_no_match.html partial → no library within 100m

    Rate-limited generously (20/5min) to absorb Library Hunt day bursts.
    """
    lat = _coerce_float(request.POST.get("lat"))
    lng = _coerce_float(request.POST.get("lng"))
    accuracy = _coerce_float(request.POST.get("accuracy"))
    accuracy_int = int(accuracy) if accuracy is not None else None

    if lat is None or lng is None or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        _log_scan("error")
        return render(request, "libraries/partials/here_no_match.html", {}, status=400)

    user_point = Point(lng, lat, srid=4326)

    # Pull candidates within 100m, ordered by distance.
    # We do a separate .count() before the slice so analytics records the
    # true number of nearby libraries — len(candidates) caps at
    # HERE_PICKER_MAX_CANDIDATES + 1, which would understate cluster density.
    candidates_qs = (
        Library.objects.filter(
            is_verified=True,
            is_active=True,
            location__distance_lte=(user_point, D(m=HERE_PICKER_RADIUS_M)),
        )
        .annotate(distance=Distance("location", user_point))
        .order_by("distance")
    )
    total_candidate_count = candidates_qs.count()
    candidates = list(candidates_qs[: HERE_PICKER_MAX_CANDIDATES + 1])

    if not candidates:
        _log_scan("no_match", user_point=user_point, accuracy=accuracy_int)
        return render(request, "libraries/partials/here_no_match.html", {})

    nearest = candidates[0]
    nearest_dist_m = nearest.distance.m

    # Decision tree for direct match vs picker.
    is_clear_winner = (
            nearest_dist_m <= HERE_DIRECT_MATCH_RADIUS_M
            and (
                    len(candidates) == 1
                    or candidates[1].distance.m - nearest_dist_m >= HERE_DISAMBIGUATION_GAP_M
            )
    )

    if is_clear_winner:
        _log_scan(
            "matched",
            matched=nearest,
            candidate_count=total_candidate_count,
            user_point=user_point,
            accuracy=accuracy_int,
        )
        response = HttpResponse("")
        response["HX-Redirect"] = nearest.get_absolute_url()
        return response

    # Picker. Trim to top N for display.
    display_candidates = candidates[:HERE_PICKER_MAX_CANDIDATES]
    _log_scan(
        "picker_shown",
        candidate_count=total_candidate_count,
        user_point=user_point,
        accuracy=accuracy_int,
    )
    return render(
        request,
        "libraries/partials/here_picker.html",
        {
            "candidates": display_candidates,
        },
    )


@require_POST
@rate_limit("here_log", limit=20, period=300)
def here_log(request):
    """
    POST /here/log/ — fire-and-forget logging of geolocation denial/error.

    Called by JS when navigator.geolocation fails (permission denied, timeout,
    position unavailable). We log the outcome so we can monitor friction.

    Rate-limited generously (20/5min) — a real user hits this once or twice
    if their permission is denied; the limit exists to prevent a bot with a
    valid CSRF token from polluting ScanEvent analytics. The fire-and-forget
    JS caller doesn't read the response, so a 429 is silently dropped.
    """
    outcome = request.POST.get("outcome", "error")
    if outcome not in {"denied", "error"}:
        outcome = "error"
    _log_scan(outcome)
    return HttpResponse("")

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