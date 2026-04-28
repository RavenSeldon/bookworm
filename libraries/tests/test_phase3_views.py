"""
Phase 3 view tests: spatial duplicate flagging in submit_library.

Run with: pytest libraries/tests/test_phase3_views.py -v

We test the ``_flag_duplicates`` helper directly rather than going through the
full HTTP submission path. The helper IS the duplicate-detection logic; the
``submit_library`` view simply calls it after creating the Shelfie. Testing
the helper in isolation gives us deterministic distance assertions without
having to wire up a fake Cloudinary backend for the photo upload.

Wiring (the call site in ``submit_library``) is verified by code review.
"""

import pytest
from django.contrib.gis.geos import Point

from libraries.models import DuplicateCandidate, Library
from libraries.views import _flag_duplicates


# Shared anchor point + offset helpers, mirroring the convention in
# test_phase2_views.py. Distances are predictable to within ~1m.
TEST_LAT = 49.2600
TEST_LNG = -123.1000

M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LNG_AT_VAN = 72_660.0


def _offset_lat(metres_north: float) -> float:
    return TEST_LAT + (metres_north / M_PER_DEG_LAT)


def _offset_lng(metres_east: float) -> float:
    return TEST_LNG + (metres_east / M_PER_DEG_LNG_AT_VAN)


def _make_library(
    *,
    name="Lib",
    metres_north=0.0,
    metres_east=0.0,
    is_verified=True,
    is_active=True,
):
    return Library.objects.create(
        name=name,
        location=Point(
            _offset_lng(metres_east),
            _offset_lat(metres_north),
            srid=4326,
        ),
        is_verified=is_verified,
        is_active=is_active,
    )


# -----------------------------------------------------------------------------
# _flag_duplicates: detection behaviour
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestFlagDuplicatesDetection:

    def test_no_existing_libraries_creates_no_candidates(self, settings):
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 30
        new_library = _make_library(name="Solo")
        # The function must not flag the library against itself.
        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 0

    def test_close_library_creates_one_candidate(self, settings):
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 30
        existing = _make_library(name="Existing", metres_east=10)
        new_library = _make_library(name="New", metres_east=15)

        _flag_duplicates(new_library)

        candidates = DuplicateCandidate.objects.all()
        assert candidates.count() == 1
        c = candidates.first()
        assert c.submitted_library == new_library
        assert c.existing_library == existing
        # ~5m apart; allow generous PostGIS rounding.
        assert 0 <= c.distance_meters <= 10
        assert c.disposition == DuplicateCandidate.PENDING

    def test_far_library_does_not_flag(self, settings):
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 20
        _make_library(name="Far", metres_east=100)
        new_library = _make_library(name="New", metres_east=0)

        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 0

    def test_self_is_excluded(self, settings):
        """A library must never flag itself, even at distance 0."""
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 30
        new_library = _make_library(name="New", metres_east=0)

        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 0

    def test_inactive_existing_library_is_excluded(self, settings):
        """Soft-deleted libraries should not produce candidates."""
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 30
        _make_library(name="Removed", metres_east=10, is_active=False)
        new_library = _make_library(name="New", metres_east=15)

        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 0

    def test_unverified_pending_library_is_INCLUDED(self, settings):
        """
        Unverified but active libraries DO match — this catches the common
        case of a user submitting twice from the same form-load. Both rows
        are unverified at that point.
        """
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 30
        _make_library(
            name="First submission",
            metres_east=10,
            is_verified=False,
            is_active=True,
        )
        new_library = _make_library(
            name="Resubmission",
            metres_east=15,
            is_verified=False,
            is_active=True,
        )

        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 1


# -----------------------------------------------------------------------------
# _flag_duplicates: ordering and capping
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestFlagDuplicatesOrderingAndCap:

    def test_caps_at_max_candidates(self, settings):
        """
        DUPLICATE_CANDIDATE_MAX limits how many rows we record per submission.
        Closest first; furthest dropped.
        """
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 50
        settings.DUPLICATE_CANDIDATE_MAX = 3

        # 5 libraries within radius at increasing distances.
        for i, dist in enumerate([5, 10, 15, 20, 25]):
            _make_library(name=f"Existing {i}", metres_east=dist)
        new_library = _make_library(name="New", metres_east=0)

        _flag_duplicates(new_library)

        candidates = list(
            DuplicateCandidate.objects.filter(submitted_library=new_library)
            .order_by("distance_meters")
        )
        assert len(candidates) == 3
        # The three closest (5m, 10m, 15m) should be flagged. Allow a few m
        # of PostGIS rounding wiggle each way.
        names = {c.existing_library.name for c in candidates}
        assert "Existing 0" in names  # 5m
        assert "Existing 1" in names  # 10m
        assert "Existing 2" in names  # 15m
        # The furthest (20m, 25m) should be dropped.
        assert "Existing 3" not in names
        assert "Existing 4" not in names

    def test_records_distance_approximately_correctly(self, settings):
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 50
        _make_library(name="Existing", metres_east=10)
        new_library = _make_library(name="New", metres_east=0)

        _flag_duplicates(new_library)

        c = DuplicateCandidate.objects.get()
        # ~10m apart. Allow PostGIS spheroid rounding.
        assert 5 <= c.distance_meters <= 15


# -----------------------------------------------------------------------------
# _flag_duplicates: resilience
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestFlagDuplicatesResilience:

    def test_uses_settings_radius(self, settings):
        """The radius is read from settings, not hardcoded."""
        # Tight radius: 5m → no flag for a 10m-away library.
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 5
        _make_library(name="Existing", metres_east=10)
        new_library = _make_library(name="New", metres_east=0)

        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 0

        # Loose radius: 50m → flags the same library.
        settings.DUPLICATE_PROXIMITY_RADIUS_M = 50
        _flag_duplicates(new_library)
        assert DuplicateCandidate.objects.count() == 1

    def test_fallback_when_settings_missing(self, settings):
        """
        getattr fallbacks (radius=20, max=3) keep the helper functional even
        if settings constants are absent.
        """
        del settings.DUPLICATE_PROXIMITY_RADIUS_M
        del settings.DUPLICATE_CANDIDATE_MAX
        _make_library(name="Existing", metres_east=10)
        new_library = _make_library(name="New", metres_east=0)

        _flag_duplicates(new_library)  # Must not raise.
        # Default radius is 20m → 10m library is in range.
        assert DuplicateCandidate.objects.count() == 1