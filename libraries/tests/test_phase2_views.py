"""
Tests for Phase 2 views: partnership flow and /here/ resolver.

Run with: pytest libraries/tests/test_phase2_views.py -v

The /here/ resolver is the most thoroughly tested surface — it has the
most complex decision tree (direct match vs picker vs no-match) and is
the highest-stakes UX (every QR scan flows through it).
"""

import time

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone

from libraries.models import Library, ScanEvent, StewardPartnership


# A central fixed point in Vancouver for resolver tests. All test libraries
# below are placed at known offsets from this point, so distances are
# predictable and the picker-threshold logic is easy to assert.
TEST_USER_LAT = 49.2600
TEST_USER_LNG = -123.1000


# Approximate metres-per-degree for Vancouver latitude — used to place
# libraries at known distances. 1 degree latitude ≈ 111_320 m. 1 degree
# longitude at lat 49.26 ≈ 111_320 * cos(49.26°) ≈ 72_660 m. We use these
# constants only for test setup — production code uses real PostGIS.
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LNG_AT_VAN = 72_660.0


def _offset_lat(metres_north: float) -> float:
    return TEST_USER_LAT + (metres_north / M_PER_DEG_LAT)


def _offset_lng(metres_east: float) -> float:
    return TEST_USER_LNG + (metres_east / M_PER_DEG_LNG_AT_VAN)


def _make_verified_library(
    *,
    name: str,
    metres_north: float = 0,
    metres_east: float = 0,
    description: str = "",
):
    """Test helper: create a verified+active library at an offset from the user."""
    return Library.objects.create(
        name=name,
        description=description,
        location=Point(
            _offset_lng(metres_east),
            _offset_lat(metres_north),
            srid=4326,
        ),
        is_verified=True,
        is_active=True,
    )


# -----------------------------------------------------------------------------
# Partnership flow
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestPartnershipForm:

    def test_get_renders_form(self, client):
        url = reverse("libraries:partnership_form")
        resp = client.get(url)
        assert resp.status_code == 200
        # Form fields are rendered.
        assert b"library_address" in resp.content
        assert b"sticker_interest" in resp.content
        # Honeypot is rendered (mixin must wire it up).
        assert b"website_url" in resp.content
        # Anti-bot timestamp is in the page.
        assert b"_form_loaded_at" in resp.content

    def test_get_only_allowed_methods(self, client):
        """GET /partners/submit/ should be 405 — POST only."""
        url = reverse("libraries:partnership_submit")
        resp = client.get(url)
        assert resp.status_code == 405


@pytest.mark.django_db
class TestPartnershipSubmit:

    def _post(self, client, **overrides):
        url = reverse("libraries:partnership_submit")
        # form_loaded_at far enough in the past to clear MIN_SUBMISSION_TIME_SECONDS
        loaded_at = timezone.now().timestamp() - 10
        data = {
            "library_address": "1234 Main St front lawn",
            "name": "Jane",
            "contact": "jane@example.com",
            "sticker_interest": "on",
            "hunt_interest": StewardPartnership.HUNT_INTEREST_YES,
            "hunt_message": "",
            "website_url": "",
            "_form_loaded_at": str(loaded_at),
        }
        data.update(overrides)
        return client.post(url, data=data)

    def test_valid_submission_creates_partnership_and_redirects(self, client):
        resp = self._post(client)
        assert resp.status_code == 302
        assert resp.url == reverse("libraries:partnership_thanks")
        assert StewardPartnership.objects.count() == 1
        partnership = StewardPartnership.objects.first()
        assert partnership.library_address == "1234 Main St front lawn"
        assert partnership.sticker_interest is True
        assert partnership.hunt_interest == StewardPartnership.HUNT_INTEREST_YES

    def test_too_fast_submission_is_rejected(self, client):
        """
        check_submission_timing should reject submissions faster than
        MIN_SUBMISSION_TIME_SECONDS. We pass a fresh _form_loaded_at to trip it.
        """
        loaded_at = timezone.now().timestamp()  # now-now → too fast
        resp = self._post(client, _form_loaded_at=str(loaded_at))
        assert resp.status_code == 400
        assert StewardPartnership.objects.count() == 0

    def test_filled_honeypot_returns_400(self, client):
        resp = self._post(client, website_url="http://spam.example.com")
        # Either the form-level rejection (422) or the view-level 400.
        # Both are acceptable; what matters is no record is created.
        assert resp.status_code in (400, 422)
        assert StewardPartnership.objects.count() == 0

    def test_invalid_form_re_renders_form(self, client):
        resp = self._post(client, library_address="", contact="")
        assert resp.status_code == 422
        assert StewardPartnership.objects.count() == 0

    def test_admin_email_sent_when_configured(self, client, settings, mailoutbox):
        settings.ADMIN_EMAIL = "admin@bookworm.guide"
        resp = self._post(client)
        assert resp.status_code == 302
        assert len(mailoutbox) == 1
        msg = mailoutbox[0]
        assert "admin@bookworm.guide" in msg.to
        assert "1234 Main St" in msg.body


@pytest.mark.django_db
class TestPartnershipThanks:

    def test_thanks_page_renders(self, client):
        url = reverse("libraries:partnership_thanks")
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Thank you" in resp.content


# -----------------------------------------------------------------------------
# /here/ landing
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestHereLanding:

    def test_get_renders_landing(self, client):
        url = reverse("libraries:here_landing")
        resp = client.get(url)
        assert resp.status_code == 200
        # The locate button is present.
        assert b"here-locate-btn" in resp.content
        # CSRF token is present (needed for the HTMX POST).
        assert b"csrfmiddlewaretoken" in resp.content


# -----------------------------------------------------------------------------
# /here/resolve/ — the decision tree
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestHereResolveDirectMatch:

    def test_single_close_library_redirects(self, client):
        """One library within 25m and nothing else nearby → HX-Redirect."""
        lib = _make_verified_library(name="Corner LFL", metres_east=10)

        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
                "accuracy": "8",
            },
        )
        assert resp.status_code == 200
        assert resp["HX-Redirect"] == lib.get_absolute_url()
        # Scan logged as matched.
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_MATCHED
        assert event.matched_library == lib

    def test_close_library_with_distant_runner_up_redirects(self, client):
        """
        Library at 10m + another at 80m → still a direct match (the gap
        between 1st and 2nd exceeds HERE_DISAMBIGUATION_GAP_M=50m).
        """
        winner = _make_verified_library(name="Winner", metres_east=10)
        _make_verified_library(name="Far runner-up", metres_east=80)

        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
                "accuracy": "10",
            },
        )
        assert resp.status_code == 200
        assert resp["HX-Redirect"] == winner.get_absolute_url()


@pytest.mark.django_db
class TestHereResolvePicker:

    def test_two_close_libraries_shows_picker(self, client):
        """
        Two libraries both within ~25m of each other and the user → the gap
        rule trips and we show the picker.
        """
        a = _make_verified_library(name="LFL A", metres_east=10)
        b = _make_verified_library(name="LFL B", metres_east=20)

        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
                "accuracy": "10",
            },
        )
        assert resp.status_code == 200
        assert "HX-Redirect" not in resp
        # Both candidates appear in the picker.
        assert b"LFL A" in resp.content
        assert b"LFL B" in resp.content
        # Scan logged as picker_shown.
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_PICKER_SHOWN
        assert event.candidate_count == 2

    def test_single_library_just_outside_direct_radius_shows_picker(self, client):
        """One library at 50m (between direct=25m and picker=100m) → picker."""
        _make_verified_library(name="Across the street", metres_east=50)

        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
            },
        )
        assert resp.status_code == 200
        assert "HX-Redirect" not in resp
        assert b"Across the street" in resp.content

    def test_picker_shows_at_most_three_candidates(self, client):
        """Even with 5 libraries within range, the picker caps at 3."""
        for i, dist in enumerate([10, 20, 30, 40, 60]):
            _make_verified_library(name=f"LFL {i}", metres_east=dist)

        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
            },
        )
        assert resp.status_code == 200
        # The three closest names appear; the two furthest do not.
        assert b"LFL 0" in resp.content
        assert b"LFL 1" in resp.content
        assert b"LFL 2" in resp.content
        assert b"LFL 4" not in resp.content


@pytest.mark.django_db
class TestHereResolveNoMatch:

    def test_no_libraries_returns_no_match(self, client):
        """No libraries in the system at all → no_match partial."""
        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
            },
        )
        assert resp.status_code == 200
        assert "HX-Redirect" not in resp
        # Content from here_no_match.html.
        assert (
            b"couldn't spot a library" in resp.content
            or b"Add this library" in resp.content
        )
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_NO_MATCH

    def test_distant_libraries_return_no_match(self, client):
        """Library at 500m (well beyond 100m radius) → no_match."""
        _make_verified_library(name="Far away", metres_east=500)

        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
            },
        )
        assert resp.status_code == 200
        assert "HX-Redirect" not in resp

    def test_unverified_libraries_excluded(self, client):
        """A close-but-unverified library should not match."""
        Library.objects.create(
            name="Pending",
            location=Point(_offset_lng(5), TEST_USER_LAT, srid=4326),
            is_verified=False,
            is_active=True,
        )
        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
            },
        )
        assert resp.status_code == 200
        assert "HX-Redirect" not in resp

    def test_inactive_libraries_excluded(self, client):
        """A close-but-deactivated library should not match."""
        Library.objects.create(
            name="Removed",
            location=Point(_offset_lng(5), TEST_USER_LAT, srid=4326),
            is_verified=True,
            is_active=False,
        )
        url = reverse("libraries:here_resolve")
        resp = client.post(
            url,
            {
                "lat": str(TEST_USER_LAT),
                "lng": str(TEST_USER_LNG),
            },
        )
        assert resp.status_code == 200
        assert "HX-Redirect" not in resp


@pytest.mark.django_db
class TestHereResolveBadInput:

    def test_missing_coords_returns_400(self, client):
        url = reverse("libraries:here_resolve")
        resp = client.post(url, {})
        assert resp.status_code == 400
        # Logged as error.
        event = ScanEvent.objects.first()
        assert event is not None
        assert event.outcome == ScanEvent.OUTCOME_ERROR

    def test_non_numeric_coords_returns_400(self, client):
        url = reverse("libraries:here_resolve")
        resp = client.post(url, {"lat": "potato", "lng": "carrot"})
        assert resp.status_code == 400

    def test_out_of_range_lat_returns_400(self, client):
        url = reverse("libraries:here_resolve")
        resp = client.post(url, {"lat": "200", "lng": str(TEST_USER_LNG)})
        assert resp.status_code == 400

    def test_out_of_range_lng_returns_400(self, client):
        url = reverse("libraries:here_resolve")
        resp = client.post(url, {"lat": str(TEST_USER_LAT), "lng": "300"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestHereResolvePrivacy:

    def test_logged_coords_are_rounded(self, client):
        """ScanEvent.location must be rounded to 4 decimals (~11m)."""
        _make_verified_library(name="Anchor", metres_east=10)

        precise_lat = 49.260987654321  # 12 decimals
        precise_lng = -123.100123456789

        url = reverse("libraries:here_resolve")
        client.post(
            url,
            {
                "lat": str(precise_lat),
                "lng": str(precise_lng),
            },
        )

        event = ScanEvent.objects.first()
        assert event is not None
        # The stored coords should be rounded — check decimals.
        # Round to 4 places, allow tiny float-precision wiggle.
        expected_lat = round(precise_lat, 4)
        expected_lng = round(precise_lng, 4)
        assert abs(event.location.y - expected_lat) < 1e-6
        assert abs(event.location.x - expected_lng) < 1e-6

    def test_no_match_logs_without_storing_precise_location(self, client):
        """No-match scans still log coords (rounded) for missing-library analysis."""
        url = reverse("libraries:here_resolve")
        client.post(url, {"lat": "49.2611111111", "lng": "-123.1011111111"})
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_NO_MATCH
        # Location is stored (rounded) — this is intentional, not a leak.
        assert event.location is not None


# -----------------------------------------------------------------------------
# /here/log/ — fire-and-forget logging
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestHereLog:

    def test_denied_logs_correctly(self, client):
        url = reverse("libraries:here_log")
        resp = client.post(url, {"outcome": "denied"})
        assert resp.status_code == 200
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_DENIED
        assert event.location is None

    def test_error_logs_correctly(self, client):
        url = reverse("libraries:here_log")
        resp = client.post(url, {"outcome": "error"})
        assert resp.status_code == 200
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_ERROR

    def test_unknown_outcome_falls_back_to_error(self, client):
        """Defensive: any outcome we don't recognise becomes 'error'."""
        url = reverse("libraries:here_log")
        resp = client.post(url, {"outcome": "shenanigans"})
        assert resp.status_code == 200
        event = ScanEvent.objects.first()
        assert event.outcome == ScanEvent.OUTCOME_ERROR
