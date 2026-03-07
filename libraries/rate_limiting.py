"""
Bookworm: Rate Limiting Utilities
=================================
Database-backed rate limiting that works across Gunicorn workers.
Includes user-friendly messages with countdown timers.
"""

import json
from functools import wraps
from datetime import datetime, timedelta

from django.core.cache import cache
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.conf import settings
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP, handling proxies (Railway, Render, etc.)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def get_rate_limit_key(key_prefix, ip):
    """Generate cache key for rate limiting."""
    return f"rate_limit:{key_prefix}:{ip}"


def get_rate_limit_info(key_prefix, ip):
    """
    Get current rate limit status for an IP.

    Returns:
        tuple: (current_count, seconds_until_reset, is_limited)
    """
    cache_key = get_rate_limit_key(key_prefix, ip)
    data = cache.get(cache_key)

    if data is None:
        return 0, 0, False

    try:
        info = json.loads(data)
        count = info.get('count', 0)
        first_request = datetime.fromisoformat(info.get('first_request'))

        # Make timezone-aware if naive
        if first_request.tzinfo is None:
            first_request = first_request.replace(tzinfo=timezone.utc)

        limit_settings = getattr(settings, 'RATE_LIMIT_SETTINGS', {})
        endpoint_settings = limit_settings.get(key_prefix, {'limit': 5, 'period': 3600})
        period = endpoint_settings['period']
        limit = endpoint_settings['limit']

        reset_time = first_request + timedelta(seconds=period)
        now = timezone.now()

        if now >= reset_time:
            cache.delete(cache_key)
            return 0, 0, False

        seconds_until_reset = max(0, int((reset_time - now).total_seconds()))
        is_limited = count >= limit

        return count, seconds_until_reset, is_limited

    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0, 0, False


def increment_rate_limit(key_prefix, ip, period):
    """Increment the rate limit counter for an IP."""
    cache_key = get_rate_limit_key(key_prefix, ip)
    data = cache.get(cache_key)

    now = timezone.now()

    if data is None:
        info = {
            'count': 1,
            'first_request': now.isoformat()
        }
    else:
        try:
            info = json.loads(data)
            first_request = datetime.fromisoformat(info.get('first_request'))
            if first_request.tzinfo is None:
                first_request = first_request.replace(tzinfo=timezone.utc)

            if now >= first_request + timedelta(seconds=period):
                info = {
                    'count': 1,
                    'first_request': now.isoformat()
                }
            else:
                info['count'] = info.get('count', 0) + 1
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            info = {
                'count': 1,
                'first_request': now.isoformat()
            }

    cache.set(cache_key, json.dumps(info), period) # Race condition present here from simultaneous requests
    return info['count']


def format_time_remaining(seconds):
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
        return f"{hours} hour{'s' if hours != 1 else ''}"


def rate_limit(key_prefix, limit=5, period=3600):
    """
    Decorator to rate limit views by IP address.

    Uses database-backed cache for consistency across Gunicorn workers.
    Returns user-friendly error messages with countdown timers.
    """
    limit_settings = getattr(settings, 'RATE_LIMIT_SETTINGS', {})
    if key_prefix in limit_settings:
        limit = limit_settings[key_prefix].get('limit', limit)
        period = limit_settings[key_prefix].get('period', period)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)

            current_count, seconds_until_reset, is_limited = get_rate_limit_info(key_prefix, ip)

            if is_limited:
                logger.warning(
                    f"Rate limit exceeded: {key_prefix}",
                    extra={
                        'ip': ip,
                        'endpoint': key_prefix,
                        'count': current_count,
                        'seconds_remaining': seconds_until_reset,
                    }
                )
                time_remaining = format_time_remaining(seconds_until_reset)
                error_message = f"You've reached the submission limit. Please try again in {time_remaining}."

                if request.headers.get('HX-Request'):
                    return TemplateResponse(
                        request,
                        'libraries/partials/rate_limited.html',
                        {
                            'message': error_message,
                            'seconds_remaining': seconds_until_reset,
                            'time_remaining': time_remaining,
                        },
                        status=429
                    )

                return JsonResponse({
                    'error': error_message,
                    'seconds_remaining': seconds_until_reset,
                    'retry_after': seconds_until_reset,
                }, status=429)

            increment_rate_limit(key_prefix, ip, period)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def check_submission_timing(request):
    """
    Check if form was submitted too quickly (bot detection).

    Returns:
        tuple: (is_suspicious, message)
    """
    form_loaded_at = request.POST.get('_form_loaded_at')

    if not form_loaded_at:
        return False, None

    try:
        loaded_time = float(form_loaded_at)
        current_time = timezone.now().timestamp()
        elapsed = current_time - loaded_time

        min_time = getattr(settings, 'MIN_SUBMISSION_TIME_SECONDS', 2)

        if elapsed < min_time:
            return True, "Please take a moment to fill out the form completely."

    except (ValueError, TypeError):
        pass

    return False, None