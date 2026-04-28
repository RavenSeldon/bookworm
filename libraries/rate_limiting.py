"""
Bookworm: Rate Limiting Utilities
=================================

Database-backed rate limiting that works across Gunicorn workers. Includes
user-friendly messages with countdown timers.

Phase 3 adds *progressive escalation*: an IP that repeatedly hits the limit
on a given key gets progressively longer timeouts (5min -> 30min -> 1h, per
the schedule in ``settings.RATE_LIMIT_ESCALATION_TIERS``). The escalation
is per-key, opt-out per-key via ``RATE_LIMIT_SETTINGS[key]['escalates']``,
and the offense tier resets after ``RATE_LIMIT_OFFENSE_WINDOW_S`` of
quiet. Honest users in the common case see no behaviour change -- the first
time anyone hits a limit they get the standard configured period.

Two cache key spaces:
  - ``rate_limit:{key}:{ip}``           -- window counter (count, first_request,
                                          effective_period). TTL = effective_period.
  - ``rate_limit_offenses:{key}:{ip}``  -- escalation tracker (tier,
                                          last_offense_at). TTL = 24h.

Bypass for trusted users: views/middleware can set
``request.bookworm_skip_rate_limit = True`` on the request before the
decorator runs. The hook is in place for the future trust-tier system; today
nothing sets it.

Known race condition: ``increment_rate_limit`` does read-then-write without
a lock; simultaneous requests can undercount. Acceptable at current scale.
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


# -----------------------------------------------------------------------------
# IP + cache key helpers
# -----------------------------------------------------------------------------


def get_client_ip(request):
    """Extract client IP, handling proxies (Railway, Render, etc.)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def get_rate_limit_key(key_prefix, ip):
    """Cache key for the window counter."""
    return f"rate_limit:{key_prefix}:{ip}"


def _get_offense_key(key_prefix, ip):
    """Cache key for the escalation tracker."""
    return f"rate_limit_offenses:{key_prefix}:{ip}"


# -----------------------------------------------------------------------------
# Settings accessors
# -----------------------------------------------------------------------------


def _get_endpoint_settings(key_prefix):
    """Return {'limit': N, 'period': P, 'escalates': bool} with sane defaults."""
    limit_settings = getattr(settings, 'RATE_LIMIT_SETTINGS', {})
    endpoint = limit_settings.get(key_prefix, {})
    return {
        'limit': endpoint.get('limit', 5),
        'period': endpoint.get('period', 3600),
        'escalates': endpoint.get('escalates', True),
    }


def _get_escalation_tiers():
    """Return the multiplier ladder, e.g. [1, 3, 6, 6]."""
    tiers = getattr(settings, 'RATE_LIMIT_ESCALATION_TIERS', [1, 3, 6, 6])
    return list(tiers) if tiers else [1]


def _get_offense_window_seconds():
    return getattr(settings, 'RATE_LIMIT_OFFENSE_WINDOW_S', 86400)


# -----------------------------------------------------------------------------
# Offense tracking
# -----------------------------------------------------------------------------


def _read_offense_tier(key_prefix, ip):
    """
    Return the current offense tier for this (key, ip), or 0 if none.
    Tier is 1-indexed externally; 0 internally means "no active offense
    record". The cache TTL handles expiry; we don't have to check timestamps
    ourselves.
    """
    raw = cache.get(_get_offense_key(key_prefix, ip))
    if not raw:
        return 0
    try:
        info = json.loads(raw)
        return int(info.get('tier', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def _bump_offense_tier(key_prefix, ip):
    """
    Register a new offense. Returns the resulting tier (1-indexed).

    Tier escalates by 1 each call, capped at len(RATE_LIMIT_ESCALATION_TIERS).
    Cache TTL renews on each bump -- the offense window is "from last offense"
    by design (a sliding window after no offenses == 24h of quiet resets you).
    """
    tiers = _get_escalation_tiers()
    cap = len(tiers)
    current = _read_offense_tier(key_prefix, ip)
    new_tier = min(current + 1, cap)
    payload = json.dumps({
        'tier': new_tier,
        'last_offense_at': timezone.now().isoformat(),
    })
    cache.set(
        _get_offense_key(key_prefix, ip),
        payload,
        _get_offense_window_seconds(),
    )
    return new_tier


def _effective_period_for_tier(base_period, tier):
    """
    Compute the effective (escalated) period for a given offense tier.

    tier=0 means no active offense record -- use base period (this happens
    on the very first block before _bump_offense_tier runs).
    tier=1 = base_period * tiers[0]; tier=N = base_period * tiers[N-1];
    above the table length we cap at the last value.
    """
    if tier <= 0:
        return base_period
    tiers = _get_escalation_tiers()
    idx = min(tier, len(tiers)) - 1
    return int(base_period * tiers[idx])


# -----------------------------------------------------------------------------
# Window counter (existing, lightly extended)
# -----------------------------------------------------------------------------


def get_rate_limit_info(key_prefix, ip, limit=None):
    """
    Get current rate limit status for an IP.

    Returns: (current_count, seconds_until_reset, is_limited)

    ``limit`` is the threshold to compare ``count`` against. The decorator
    passes its already-resolved value (which honours decorator args for
    unknown keys, settings-overrides for known keys). When called without
    ``limit``, falls back to ``_get_endpoint_settings`` -- this preserves
    backward compatibility for any external caller, though we don't have
    any in-tree.

    Reads the counter's stored ``effective_period`` (set when the entry was
    written, possibly after escalation) so the window length -- and the
    countdown shown to the user -- reflects the *current* tier, not the
    base period.
    """
    cache_key = get_rate_limit_key(key_prefix, ip)
    data = cache.get(cache_key)

    if data is None:
        return 0, 0, False

    try:
        info = json.loads(data)
        count = int(info.get('count', 0))
        first_request = datetime.fromisoformat(info.get('first_request'))
        if first_request.tzinfo is None:
            first_request = first_request.replace(tzinfo=timezone.utc)

        endpoint = _get_endpoint_settings(key_prefix)
        # Prefer the stored effective_period (post-escalation). Fall back to
        # the configured base period for any legacy entries written before
        # this field existed.
        effective_period = int(info.get('effective_period', endpoint['period']))
        if limit is None:
            limit = endpoint['limit']

        reset_time = first_request + timedelta(seconds=effective_period)
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
    """
    Increment the rate limit counter for an IP.

    NOTE: ``period`` here is the *effective* period for the active tier --
    the decorator passes whatever it computed (either base or escalated).
    The counter's TTL and stored ``effective_period`` track that, so a user
    on tier 2 sees a 30min window, not 10min.

    Known race condition: read-then-write without a lock; simultaneous
    requests can undercount. Acceptable at current scale.
    """
    cache_key = get_rate_limit_key(key_prefix, ip)
    data = cache.get(cache_key)
    now = timezone.now()

    if data is None:
        info = {
            'count': 1,
            'first_request': now.isoformat(),
            'effective_period': int(period),
            'offense_registered': False,
        }
    else:
        try:
            info = json.loads(data)
            first_request = datetime.fromisoformat(info.get('first_request'))
            if first_request.tzinfo is None:
                first_request = first_request.replace(tzinfo=timezone.utc)

            stored_period = int(info.get('effective_period', period))
            if now >= first_request + timedelta(seconds=stored_period):
                # Window expired -- start fresh at the (possibly new) period.
                info = {
                    'count': 1,
                    'first_request': now.isoformat(),
                    'effective_period': int(period),
                    'offense_registered': False,
                }
            else:
                info['count'] = int(info.get('count', 0)) + 1
                info.setdefault('effective_period', int(period))
                info.setdefault('offense_registered', False)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            info = {
                'count': 1,
                'first_request': now.isoformat(),
                'effective_period': int(period),
                'offense_registered': False,
            }

    cache.set(cache_key, json.dumps(info), info['effective_period'])
    return info['count']


def _mark_offense_registered(key_prefix, ip):
    """
    Set ``offense_registered=True`` on the current window counter so we
    only escalate once per blocked window, not once per blocked request.

    Also rewrites ``effective_period`` to the post-escalation value so
    ``get_rate_limit_info`` surfaces the new countdown to the user. The
    cache TTL is reset to the new period to keep the window alive long
    enough for the user to see it expire.
    """
    cache_key = get_rate_limit_key(key_prefix, ip)
    data = cache.get(cache_key)
    if not data:
        return
    try:
        info = json.loads(data)
    except (json.JSONDecodeError, ValueError, TypeError):
        return
    info['offense_registered'] = True

    base_period = _get_endpoint_settings(key_prefix)['period']
    tier = _read_offense_tier(key_prefix, ip)
    info['effective_period'] = _effective_period_for_tier(base_period, tier)

    cache.set(cache_key, json.dumps(info), info['effective_period'])


def _is_offense_already_registered(key_prefix, ip):
    """Has this user's current limit-window already triggered an escalation?"""
    data = cache.get(get_rate_limit_key(key_prefix, ip))
    if not data:
        return False
    try:
        return bool(json.loads(data).get('offense_registered', False))
    except (json.JSONDecodeError, ValueError, TypeError):
        return False


# -----------------------------------------------------------------------------
# User-facing formatting
# -----------------------------------------------------------------------------


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


# -----------------------------------------------------------------------------
# Decorator
# -----------------------------------------------------------------------------


def rate_limit(key_prefix, limit=5, period=3600):
    """
    Decorator to rate limit views by IP address.

    Phase 3: progressive escalation. On the first hit-of-limit in a fresh
    window, we register an offense (bumping the tier) and the window's
    effective period grows accordingly. Subsequent blocks within that
    same window do not re-escalate. After ``RATE_LIMIT_OFFENSE_WINDOW_S``
    of no further blocks, the tier resets.

    Settings overrides ``limit`` and ``period`` if the key is in
    RATE_LIMIT_SETTINGS -- same as before. Decorator signature unchanged.

    Bypass: views/middleware can set ``request.bookworm_skip_rate_limit =
    True`` on the request to skip both the check and offense registration.
    Hook for future trust tiers; nothing sets it today.
    """
    # Settings override decorator args ONLY when the key is explicitly
    # configured. Without this guard, an unknown key would silently fall
    # through to _get_endpoint_settings's hardcoded defaults (5/3600) and
    # ignore whatever limit/period the caller passed.
    limit_settings = getattr(settings, 'RATE_LIMIT_SETTINGS', {})
    if key_prefix in limit_settings:
        limit = limit_settings[key_prefix].get('limit', limit)
        period = limit_settings[key_prefix].get('period', period)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if getattr(request, 'bookworm_skip_rate_limit', False):
                return view_func(request, *args, **kwargs)

            ip = get_client_ip(request)
            current_count, seconds_until_reset, is_limited = (
                get_rate_limit_info(key_prefix, ip, limit=limit)
            )

            if is_limited:
                # Register an offense at most once per blocked window.
                escalates = _get_endpoint_settings(key_prefix)['escalates']
                if escalates and not _is_offense_already_registered(key_prefix, ip):
                    new_tier = _bump_offense_tier(key_prefix, ip)
                    _mark_offense_registered(key_prefix, ip)
                    # Re-read so the user sees the freshly-escalated countdown.
                    _, seconds_until_reset, _ = get_rate_limit_info(
                        key_prefix, ip, limit=limit
                    )
                    logger.warning(
                        f"Rate limit escalation: {key_prefix}",
                        extra={
                            'ip': ip,
                            'endpoint': key_prefix,
                            'tier': new_tier,
                            'seconds_remaining': seconds_until_reset,
                        }
                    )
                else:
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
                error_message = (
                    f"You've reached the submission limit. "
                    f"Please try again in {time_remaining}."
                )

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

            # Not limited -- increment using the *current* effective period.
            # On a fresh window this is the base period; on a window already
            # escalated by a prior offense it's the escalated period.
            current_tier = _read_offense_tier(key_prefix, ip)
            effective_period = _effective_period_for_tier(period, current_tier)
            increment_rate_limit(key_prefix, ip, effective_period)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# -----------------------------------------------------------------------------
# Anti-bot timing
# -----------------------------------------------------------------------------


def check_submission_timing(request):
    """
    Check if form was submitted too quickly (bot detection).

    Returns: (is_suspicious, message)
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
