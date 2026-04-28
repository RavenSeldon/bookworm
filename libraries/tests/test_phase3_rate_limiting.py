"""
Phase 3 rate-limiting tests: progressive escalation and bypass.

Run with: pytest libraries/tests/test_phase3_rate_limiting.py -v

We test the helpers (``_bump_offense_tier``, ``_effective_period_for_tier``,
``_read_offense_tier``) directly, and the decorator end-to-end via a tiny
test view registered against a stub urlconf.

Cache hygiene is critical: ``DatabaseCache`` is shared across tests under
``--reuse-db``. The ``cache_clear`` fixture below wipes the rate-limit
namespace before every test so leftover counters from a prior test can't
mask escalation behaviour.
"""

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path

from libraries import rate_limiting as rl
from libraries.rate_limiting import (
    _bump_offense_tier,
    _effective_period_for_tier,
    _read_offense_tier,
    _mark_offense_registered,
    _is_offense_already_registered,
    get_rate_limit_info,
    rate_limit,
)


# -----------------------------------------------------------------------------
# Shared fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cache_clear(db):
    """Wipe the cache before each test. Required for deterministic rate-limit state."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def rf():
    return RequestFactory()


def _make_request(rf, ip="1.2.3.4", htmx=False):
    """A minimal POST request with a known IP."""
    headers = {"REMOTE_ADDR": ip}
    if htmx:
        headers["HTTP_HX_REQUEST"] = "true"
    return rf.post("/test/", **headers)


def _make_view(key_prefix, limit, period, escalates=True):
    """
    Build a decorated view inline. We bake the key into RATE_LIMIT_SETTINGS
    via the settings fixture in each test rather than here -- that way the
    decorator picks up the right limit/period/escalates from settings.
    """
    @rate_limit(key_prefix, limit=limit, period=period)
    def view(request):
        return HttpResponse("ok")
    return view


def _set_settings(settings, *, key="test_key", limit=2, period=60,
                  escalates=True, tiers=(1, 3, 6, 6),
                  offense_window=86400):
    """Configure the rate-limit settings dict for a test."""
    settings.RATE_LIMIT_SETTINGS = {
        key: {"limit": limit, "period": period, "escalates": escalates},
    }
    settings.RATE_LIMIT_ESCALATION_TIERS = list(tiers)
    settings.RATE_LIMIT_OFFENSE_WINDOW_S = offense_window


# -----------------------------------------------------------------------------
# Helper unit tests (pure functions)
# -----------------------------------------------------------------------------


class TestEffectivePeriodForTier:

    def test_tier_zero_returns_base(self, settings):
        settings.RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]
        assert _effective_period_for_tier(600, 0) == 600

    def test_tier_one_uses_first_multiplier(self, settings):
        settings.RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]
        assert _effective_period_for_tier(600, 1) == 600

    def test_tier_two_uses_second_multiplier(self, settings):
        settings.RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]
        assert _effective_period_for_tier(600, 2) == 1800

    def test_tier_three_uses_third_multiplier(self, settings):
        settings.RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]
        assert _effective_period_for_tier(600, 3) == 3600

    def test_tier_above_table_caps_at_last(self, settings):
        settings.RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]
        # tier 4, 5, 99 all clamp to tiers[-1] = 6
        assert _effective_period_for_tier(600, 4) == 3600
        assert _effective_period_for_tier(600, 99) == 3600


class TestBumpOffenseTier:

    def test_first_bump_sets_tier_one(self, settings):
        _set_settings(settings)
        assert _read_offense_tier("test_key", "1.2.3.4") == 0
        new = _bump_offense_tier("test_key", "1.2.3.4")
        assert new == 1
        assert _read_offense_tier("test_key", "1.2.3.4") == 1

    def test_repeated_bumps_escalate(self, settings):
        _set_settings(settings)
        assert _bump_offense_tier("test_key", "1.2.3.4") == 1
        assert _bump_offense_tier("test_key", "1.2.3.4") == 2
        assert _bump_offense_tier("test_key", "1.2.3.4") == 3
        assert _bump_offense_tier("test_key", "1.2.3.4") == 4

    def test_caps_at_tier_table_length(self, settings):
        _set_settings(settings, tiers=(1, 3, 6, 6))
        for _ in range(10):
            tier = _bump_offense_tier("test_key", "1.2.3.4")
        assert tier == 4  # len(tiers)

    def test_per_key_isolation(self, settings):
        _set_settings(settings)
        # Two keys, same IP -- tracked independently.
        settings.RATE_LIMIT_SETTINGS["other_key"] = {
            "limit": 2, "period": 60, "escalates": True
        }
        _bump_offense_tier("test_key", "1.2.3.4")
        _bump_offense_tier("test_key", "1.2.3.4")
        _bump_offense_tier("other_key", "1.2.3.4")
        assert _read_offense_tier("test_key", "1.2.3.4") == 2
        assert _read_offense_tier("other_key", "1.2.3.4") == 1

    def test_per_ip_isolation(self, settings):
        _set_settings(settings)
        _bump_offense_tier("test_key", "1.2.3.4")
        _bump_offense_tier("test_key", "1.2.3.4")
        _bump_offense_tier("test_key", "5.6.7.8")
        assert _read_offense_tier("test_key", "1.2.3.4") == 2
        assert _read_offense_tier("test_key", "5.6.7.8") == 1


# -----------------------------------------------------------------------------
# Decorator end-to-end behaviour
# -----------------------------------------------------------------------------


class TestDecoratorBaseline:
    """First-time block: no prior offenses, should behave like the old system."""

    def test_first_three_requests_under_limit_pass(self, settings, rf):
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)
        # Two requests pass.
        assert view(_make_request(rf)).status_code == 200
        assert view(_make_request(rf)).status_code == 200
        # Third hits the limit.
        resp = view(_make_request(rf))
        assert resp.status_code == 429

    def test_first_block_escalates_to_tier_one(self, settings, rf):
        """The first block in a fresh window registers an offense (tier 1)."""
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)
        view(_make_request(rf))
        view(_make_request(rf))
        view(_make_request(rf))  # blocked, registers tier 1
        assert _read_offense_tier("test_key", "1.2.3.4") == 1


class TestDecoratorEscalation:
    """Repeated offenses across separate windows climb the tier ladder."""

    def test_subsequent_blocks_in_same_window_do_not_re_escalate(self, settings, rf):
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)
        view(_make_request(rf))
        view(_make_request(rf))
        # Spam-block ten times in the same window.
        for _ in range(10):
            resp = view(_make_request(rf))
            assert resp.status_code == 429
        # Tier should not have moved past 1.
        assert _read_offense_tier("test_key", "1.2.3.4") == 1

    def test_window_expiry_resets_counter_then_new_block_escalates(
        self, settings, rf, monkeypatch
    ):
        """
        Force the window counter to expire (by deleting it directly), then
        hit the limit again from a fresh state. Tier should bump to 2 because
        the offense record is still alive.
        """
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)
        view(_make_request(rf))
        view(_make_request(rf))
        view(_make_request(rf))  # blocked, tier 1

        # Simulate the window expiring without the offense expiring.
        cache.delete(rl.get_rate_limit_key("test_key", "1.2.3.4"))

        # Fresh window: two passes, third blocks, should bump to tier 2.
        view(_make_request(rf))
        view(_make_request(rf))
        view(_make_request(rf))  # blocked again
        assert _read_offense_tier("test_key", "1.2.3.4") == 2

    def test_three_offenses_reach_tier_three(self, settings, rf):
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)

        for _ in range(3):
            cache.delete(rl.get_rate_limit_key("test_key", "1.2.3.4"))
            view(_make_request(rf))
            view(_make_request(rf))
            view(_make_request(rf))  # blocked

        assert _read_offense_tier("test_key", "1.2.3.4") == 3

    def test_tier_caps_at_table_length(self, settings, rf):
        """Beyond the table length, tier must not grow further."""
        _set_settings(settings, limit=2, period=60, tiers=(1, 3, 6, 6))
        view = _make_view("test_key", limit=2, period=60)

        for _ in range(8):
            cache.delete(rl.get_rate_limit_key("test_key", "1.2.3.4"))
            view(_make_request(rf))
            view(_make_request(rf))
            view(_make_request(rf))

        assert _read_offense_tier("test_key", "1.2.3.4") == 4


class TestDecoratorEffectivePeriodSurfaced:
    """The 429 response must reflect the *escalated* period, not the base."""

    def test_blocked_response_shows_escalated_countdown(self, settings, rf):
        _set_settings(settings, limit=2, period=60, tiers=(1, 3, 6, 6))
        view = _make_view("test_key", limit=2, period=60)
        view(_make_request(rf))
        view(_make_request(rf))
        view(_make_request(rf))  # tier 1 (1x = 60s)

        # Fresh window, second offense -> tier 2 -> 60s * 3 = 180s.
        cache.delete(rl.get_rate_limit_key("test_key", "1.2.3.4"))
        view(_make_request(rf))
        view(_make_request(rf))
        resp = view(_make_request(rf))  # blocked, escalation runs
        assert resp.status_code == 429

        # The window counter should now record the escalated period.
        _, seconds_remaining, _ = get_rate_limit_info("test_key", "1.2.3.4")
        # Within ~5s of 180 (the test took some real time).
        assert 170 <= seconds_remaining <= 180

    def test_offense_registered_marker_set_after_block(self, settings, rf):
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)
        view(_make_request(rf))
        view(_make_request(rf))
        view(_make_request(rf))  # blocked
        assert _is_offense_already_registered("test_key", "1.2.3.4") is True


class TestDecoratorOptOut:
    """Endpoints with escalates=False stay flat regardless of repeat offenses."""

    def test_escalates_false_does_not_bump_tier(self, settings, rf):
        _set_settings(settings, limit=2, period=60, escalates=False)
        view = _make_view("test_key", limit=2, period=60)

        for _ in range(5):
            cache.delete(rl.get_rate_limit_key("test_key", "1.2.3.4"))
            view(_make_request(rf))
            view(_make_request(rf))
            resp = view(_make_request(rf))
            assert resp.status_code == 429

        # No offense record should exist.
        assert _read_offense_tier("test_key", "1.2.3.4") == 0

    def test_escalates_false_uses_base_period(self, settings, rf):
        """The 429 countdown must reflect the base period, not any escalation."""
        _set_settings(settings, limit=2, period=60, escalates=False)
        view = _make_view("test_key", limit=2, period=60)
        view(_make_request(rf))
        view(_make_request(rf))
        view(_make_request(rf))  # blocked

        _, seconds_remaining, _ = get_rate_limit_info("test_key", "1.2.3.4")
        assert 50 <= seconds_remaining <= 60


class TestDecoratorBypass:
    """Trust-tier hook: bookworm_skip_rate_limit attr disables the limit."""

    def test_bypass_attr_skips_limit_check(self, settings, rf):
        _set_settings(settings, limit=1, period=60)
        view = _make_view("test_key", limit=1, period=60)

        # Burn through the limit on a normal request.
        view(_make_request(rf))
        # Now a bypassing request should NOT 429.
        request = _make_request(rf)
        request.bookworm_skip_rate_limit = True
        resp = view(request)
        assert resp.status_code == 200

    def test_bypass_attr_does_not_increment_counter(self, settings, rf):
        """A bypass call must not contribute to the limit count for others."""
        _set_settings(settings, limit=2, period=60)
        view = _make_view("test_key", limit=2, period=60)

        # Send 5 bypass requests.
        for _ in range(5):
            request = _make_request(rf)
            request.bookworm_skip_rate_limit = True
            view(request)

        # A normal user should still get 2 requests through.
        assert view(_make_request(rf)).status_code == 200
        assert view(_make_request(rf)).status_code == 200
        assert view(_make_request(rf)).status_code == 429

    def test_bypass_attr_does_not_register_offense(self, settings, rf):
        """A bypassing user must never accumulate a tier."""
        _set_settings(settings, limit=1, period=60)
        view = _make_view("test_key", limit=1, period=60)

        for _ in range(10):
            request = _make_request(rf)
            request.bookworm_skip_rate_limit = True
            view(request)

        assert _read_offense_tier("test_key", "1.2.3.4") == 0


class TestDecoratorBackwardCompat:
    """Existing call sites (no settings, no escalation hints) must keep working."""

    def test_unknown_key_uses_decorator_defaults(self, settings, rf):
        # No entry in RATE_LIMIT_SETTINGS for this key.
        settings.RATE_LIMIT_SETTINGS = {}
        settings.RATE_LIMIT_ESCALATION_TIERS = [1, 3, 6, 6]
        settings.RATE_LIMIT_OFFENSE_WINDOW_S = 86400

        view = _make_view("unknown_key", limit=2, period=60)
        assert view(_make_request(rf)).status_code == 200
        assert view(_make_request(rf)).status_code == 200
        assert view(_make_request(rf)).status_code == 429

    def test_settings_override_decorator_args(self, settings, rf):
        """If the key is in settings, settings.limit wins over decorator arg."""
        _set_settings(settings, limit=1, period=60)
        # Decorator args say limit=99, but settings says 1.
        view = _make_view("test_key", limit=99, period=60)
        assert view(_make_request(rf)).status_code == 200
        # Second request should be blocked.
        assert view(_make_request(rf)).status_code == 429
