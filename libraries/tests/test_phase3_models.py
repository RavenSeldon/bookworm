"""
Phase 3 model tests: DuplicateCandidate + Library.merged_into.

Run with: pytest libraries/tests/test_phase3_models.py -v
"""

import pytest
from django.contrib.gis.geos import Point

from libraries.models import DuplicateCandidate, Library


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _make_library(name="Test", lng=-123.1207, lat=49.2827, **kwargs):
    """Bare Library factory; tests that don't use conftest fixtures use this."""
    library = Library(
        name=name,
        location=Point(lng, lat, srid=4326),
        is_verified=kwargs.pop("is_verified", True),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
    library.save()
    return library


# -----------------------------------------------------------------------------
# DuplicateCandidate model
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestDuplicateCandidateBasics:

    def test_create_with_defaults(self):
        a = _make_library(name="A")
        b = _make_library(name="B", lng=-123.1208)
        candidate = DuplicateCandidate.objects.create(
            submitted_library=a,
            existing_library=b,
            distance_meters=12,
        )
        assert candidate.disposition == DuplicateCandidate.PENDING
        assert candidate.is_pending is True
        assert candidate.resolved_at is None
        assert candidate.admin_notes == ""
        assert candidate.created_at is not None

    def test_str_format(self):
        a = _make_library(name="Submitted")
        b = _make_library(name="Existing", lng=-123.1208)
        candidate = DuplicateCandidate.objects.create(
            submitted_library=a,
            existing_library=b,
            distance_meters=15,
        )
        s = str(candidate)
        assert f"#{a.pk}" in s
        assert f"#{b.pk}" in s
        assert "15m" in s
        assert "Pending review" in s

    def test_disposition_choices_complete(self):
        """All four dispositions are accepted by the model."""
        a = _make_library(name="A")
        b = _make_library(name="B", lng=-123.1208)
        for disposition, _label in DuplicateCandidate.DISPOSITION_CHOICES:
            candidate = DuplicateCandidate.objects.create(
                submitted_library=a,
                existing_library=b,
                distance_meters=10,
                disposition=disposition,
            )
            candidate.refresh_from_db()
            assert candidate.disposition == disposition
            candidate.delete()

    def test_is_pending_helper(self):
        a = _make_library(name="A")
        b = _make_library(name="B", lng=-123.1208)
        c = DuplicateCandidate.objects.create(
            submitted_library=a, existing_library=b, distance_meters=5,
        )
        assert c.is_pending is True
        c.disposition = DuplicateCandidate.MERGED
        c.save()
        assert c.is_pending is False

    def test_ordering_newest_first(self):
        a = _make_library(name="A")
        b = _make_library(name="B", lng=-123.1208)
        first = DuplicateCandidate.objects.create(
            submitted_library=a, existing_library=b, distance_meters=5,
        )
        second = DuplicateCandidate.objects.create(
            submitted_library=a, existing_library=b, distance_meters=10,
        )
        ordered = list(DuplicateCandidate.objects.all())
        assert ordered[0].pk == second.pk
        assert ordered[1].pk == first.pk

    def test_related_names(self):
        """Both FKs use distinct related_names so reverse lookups don't collide."""
        a = _make_library(name="A")
        b = _make_library(name="B", lng=-123.1208)
        DuplicateCandidate.objects.create(
            submitted_library=a, existing_library=b, distance_meters=5,
        )
        # Submitted library sees it via duplicate_candidates
        assert a.duplicate_candidates.count() == 1
        # Existing library sees it via duplicate_matches
        assert b.duplicate_matches.count() == 1
        # And not crossed
        assert a.duplicate_matches.count() == 0
        assert b.duplicate_candidates.count() == 0

    def test_cascade_on_library_deletion(self):
        """Deleting a library deletes its candidate rows (CASCADE)."""
        a = _make_library(name="A")
        b = _make_library(name="B", lng=-123.1208)
        DuplicateCandidate.objects.create(
            submitted_library=a, existing_library=b, distance_meters=5,
        )
        assert DuplicateCandidate.objects.count() == 1
        a.delete()
        assert DuplicateCandidate.objects.count() == 0


# -----------------------------------------------------------------------------
# Library.merged_into FK
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestLibraryMergedInto:

    def test_default_is_null(self):
        lib = _make_library(name="Solo")
        assert lib.merged_into is None
        assert lib.merged_from.count() == 0

    def test_merged_into_round_trip(self):
        survivor = _make_library(name="Survivor")
        doomed = _make_library(name="Doomed", lng=-123.1208)
        doomed.merged_into = survivor
        doomed.is_active = False
        doomed.save()

        doomed.refresh_from_db()
        assert doomed.merged_into == survivor
        # Reverse relation
        assert list(survivor.merged_from.all()) == [doomed]

    def test_set_null_on_target_delete(self):
        """If the survivor is later deleted, merged_into goes to NULL not cascade."""
        survivor = _make_library(name="Survivor")
        doomed = _make_library(name="Doomed", lng=-123.1208)
        doomed.merged_into = survivor
        doomed.save()

        survivor.delete()
        doomed.refresh_from_db()
        # The doomed row survives — its merged_into is just nulled.
        assert doomed.pk is not None
        assert doomed.merged_into is None
