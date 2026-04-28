"""
Phase 3 admin tests: DuplicateCandidate bulk actions.

Run with: pytest libraries/tests/test_phase3_admin.py -v

Covers ``approve_as_new`` and ``reject``. The merge action is Phase 3 P2 and
has its own tests once implemented.

Actions are invoked directly on the admin instance (rather than through the
Django admin HTTP layer) for speed and to avoid auth setup. ``message_user``
is stubbed because it expects a real request with a messages backend.
"""

import pytest
from django.contrib.admin.sites import site
from django.contrib.gis.geos import Point
from django.utils import timezone

from libraries.admin import DuplicateCandidateAdmin
from libraries.models import (
    DuplicateCandidate,
    IssueReport,
    Library,
    Shelfie,
    StewardPartnership,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


class _StubRequest:
    """Minimal stand-in for an admin request."""
    def __init__(self):
        self.user = None


@pytest.fixture
def admin_instance(monkeypatch):
    """An admin instance with message_user neutered."""
    instance = DuplicateCandidateAdmin(DuplicateCandidate, site)
    monkeypatch.setattr(
        instance, "message_user", lambda *args, **kwargs: None
    )
    return instance


def _make_library(name, lng_offset=0.0):
    library = Library(
        name=name,
        location=Point(-123.1207 + lng_offset, 49.2827, srid=4326),
        is_verified=True,
        is_active=True,
    )
    library.save()
    return library


def _make_candidate(submitted=None, existing=None, **kwargs):
    submitted = submitted or _make_library("Submitted")
    existing = existing or _make_library("Existing", lng_offset=0.0001)
    return DuplicateCandidate.objects.create(
        submitted_library=submitted,
        existing_library=existing,
        distance_meters=kwargs.pop("distance_meters", 10),
        **kwargs,
    )


# -----------------------------------------------------------------------------
# approve_as_new
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestApproveAsNew:

    def test_marks_disposition_and_resolved_at(self, admin_instance):
        candidate = _make_candidate()
        before = timezone.now()
        admin_instance.approve_as_new(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )
        candidate.refresh_from_db()
        assert candidate.disposition == DuplicateCandidate.APPROVED_NEW
        assert candidate.resolved_at is not None
        assert candidate.resolved_at >= before

    def test_does_not_touch_libraries(self, admin_instance):
        """Approving as new must not modify either library record."""
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        candidate = _make_candidate(submitted=submitted, existing=existing)

        admin_instance.approve_as_new(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        submitted.refresh_from_db()
        existing.refresh_from_db()
        assert submitted.is_active is True
        assert submitted.is_verified is True
        assert existing.is_active is True
        assert existing.is_verified is True

    def test_skips_already_resolved_candidates(self, admin_instance):
        """An already-merged candidate must not be re-resolved."""
        candidate = _make_candidate()
        candidate.disposition = DuplicateCandidate.MERGED
        candidate.resolved_at = timezone.now()
        candidate.save()
        original_disposition = candidate.disposition
        original_resolved = candidate.resolved_at

        admin_instance.approve_as_new(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        candidate.refresh_from_db()
        assert candidate.disposition == original_disposition
        assert candidate.resolved_at == original_resolved

    def test_handles_multiple_candidates(self, admin_instance):
        c1 = _make_candidate()
        c2 = _make_candidate()
        admin_instance.approve_as_new(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk__in=[c1.pk, c2.pk]),
        )
        c1.refresh_from_db()
        c2.refresh_from_db()
        assert c1.disposition == DuplicateCandidate.APPROVED_NEW
        assert c2.disposition == DuplicateCandidate.APPROVED_NEW


# -----------------------------------------------------------------------------
# reject
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestReject:

    def test_deactivates_submitted_library(self, admin_instance):
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        candidate = _make_candidate(submitted=submitted, existing=existing)

        admin_instance.reject(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        submitted.refresh_from_db()
        existing.refresh_from_db()
        # Submitted is soft-deleted.
        assert submitted.is_active is False
        # Existing is untouched.
        assert existing.is_active is True

    def test_marks_disposition_and_resolved_at(self, admin_instance):
        candidate = _make_candidate()
        before = timezone.now()
        admin_instance.reject(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )
        candidate.refresh_from_db()
        assert candidate.disposition == DuplicateCandidate.REJECTED
        assert candidate.resolved_at is not None
        assert candidate.resolved_at >= before

    def test_skips_already_resolved(self, admin_instance):
        """A previously-merged candidate must not have its submitted lib touched."""
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        candidate = _make_candidate(submitted=submitted, existing=existing)
        candidate.disposition = DuplicateCandidate.APPROVED_NEW
        candidate.resolved_at = timezone.now()
        candidate.save()

        admin_instance.reject(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        submitted.refresh_from_db()
        candidate.refresh_from_db()
        assert submitted.is_active is True
        assert candidate.disposition == DuplicateCandidate.APPROVED_NEW

    def test_handles_multiple_candidates(self, admin_instance):
        c1 = _make_candidate()
        c2 = _make_candidate()
        admin_instance.reject(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk__in=[c1.pk, c2.pk]),
        )
        c1.refresh_from_db()
        c2.refresh_from_db()
        assert c1.disposition == DuplicateCandidate.REJECTED
        assert c2.disposition == DuplicateCandidate.REJECTED
        # Both submitted libraries deactivated.
        assert c1.submitted_library.is_active is False
        assert c2.submitted_library.is_active is False


# -----------------------------------------------------------------------------
# merge_into_existing
# -----------------------------------------------------------------------------


@pytest.mark.django_db
class TestMergeIntoExisting:

    def test_reassigns_shelfies(self, admin_instance):
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        s1 = Shelfie.objects.create(
            library=submitted, photo="bookworm/shelfies/s1",
        )
        s2 = Shelfie.objects.create(
            library=submitted, photo="bookworm/shelfies/s2",
        )
        candidate = _make_candidate(submitted=submitted, existing=existing)

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        s1.refresh_from_db()
        s2.refresh_from_db()
        assert s1.library_id == existing.pk
        assert s2.library_id == existing.pk
        # No orphan shelfies on the doomed library.
        assert submitted.shelfies.count() == 0

    def test_reassigns_issue_reports(self, admin_instance):
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        report = IssueReport.objects.create(
            library=submitted,
            issue_type="wrong_location",
            description="Should follow the merge",
        )
        candidate = _make_candidate(submitted=submitted, existing=existing)

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        report.refresh_from_db()
        assert report.library_id == existing.pk

    def test_reassigns_steward_partnerships(self, admin_instance):
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        partnership = StewardPartnership.objects.create(
            library_address="front lawn of 1234 Main",
            contact="steward@example.com",
            library=submitted,
        )
        candidate = _make_candidate(submitted=submitted, existing=existing)

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        partnership.refresh_from_db()
        assert partnership.library_id == existing.pk

    def test_deactivates_submitted_and_sets_merged_into(self, admin_instance):
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        candidate = _make_candidate(submitted=submitted, existing=existing)

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        submitted.refresh_from_db()
        existing.refresh_from_db()
        assert submitted.is_active is False
        assert submitted.merged_into_id == existing.pk
        # Existing is untouched in identity.
        assert existing.is_active is True
        assert existing.is_verified is True

    def test_promotes_last_updated_when_submitted_is_fresher(self, admin_instance):
        """If the doomed row has a fresher last_updated, the survivor adopts it."""
        from datetime import timedelta

        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        # Make existing stale, submitted fresh.
        old = timezone.now() - timedelta(days=30)
        recent = timezone.now() - timedelta(days=1)
        Library.objects.filter(pk=existing.pk).update(last_updated=old)
        Library.objects.filter(pk=submitted.pk).update(last_updated=recent)

        candidate = _make_candidate(submitted=submitted, existing=existing)
        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        existing.refresh_from_db()
        # Allow microsecond-level wiggle from the round trip.
        assert abs((existing.last_updated - recent).total_seconds()) < 1

    def test_does_not_demote_last_updated(self, admin_instance):
        """If the survivor was already fresher, last_updated is NOT lowered."""
        from datetime import timedelta

        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        old = timezone.now() - timedelta(days=30)
        recent = timezone.now() - timedelta(days=1)
        Library.objects.filter(pk=existing.pk).update(last_updated=recent)
        Library.objects.filter(pk=submitted.pk).update(last_updated=old)

        candidate = _make_candidate(submitted=submitted, existing=existing)
        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        existing.refresh_from_db()
        assert abs((existing.last_updated - recent).total_seconds()) < 1

    def test_marks_candidate_merged_with_resolved_at(self, admin_instance):
        candidate = _make_candidate()
        before = timezone.now()
        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )
        candidate.refresh_from_db()
        assert candidate.disposition == DuplicateCandidate.MERGED
        assert candidate.resolved_at is not None
        assert candidate.resolved_at >= before

    def test_auto_resolves_sibling_candidates(self, admin_instance):
        """
        When one submission flagged 3 existing libraries, merging into the
        chosen one auto-resolves the other two pending candidates — they
        all point at the same now-merged submission.
        """
        submitted = _make_library("Submitted")
        chosen = _make_library("Chosen survivor", lng_offset=0.0001)
        sibling_a = _make_library("Sibling A", lng_offset=0.0002)
        sibling_b = _make_library("Sibling B", lng_offset=0.0003)

        merged_candidate = DuplicateCandidate.objects.create(
            submitted_library=submitted, existing_library=chosen,
            distance_meters=8,
        )
        sib_a = DuplicateCandidate.objects.create(
            submitted_library=submitted, existing_library=sibling_a,
            distance_meters=12,
        )
        sib_b = DuplicateCandidate.objects.create(
            submitted_library=submitted, existing_library=sibling_b,
            distance_meters=18,
        )

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=merged_candidate.pk),
        )

        merged_candidate.refresh_from_db()
        sib_a.refresh_from_db()
        sib_b.refresh_from_db()
        assert merged_candidate.disposition == DuplicateCandidate.MERGED
        # Siblings are auto-resolved as MERGED too — the submission is gone.
        assert sib_a.disposition == DuplicateCandidate.MERGED
        assert sib_a.resolved_at is not None
        assert sib_b.disposition == DuplicateCandidate.MERGED
        assert sib_b.resolved_at is not None

    def test_does_not_auto_resolve_unrelated_candidates(self, admin_instance):
        """Sibling auto-resolve must not touch candidates from OTHER submissions."""
        submitted_a = _make_library("Sub A")
        submitted_b = _make_library("Sub B", lng_offset=0.0005)
        existing = _make_library("Existing", lng_offset=0.0001)

        merged_candidate = DuplicateCandidate.objects.create(
            submitted_library=submitted_a, existing_library=existing,
            distance_meters=8,
        )
        unrelated = DuplicateCandidate.objects.create(
            submitted_library=submitted_b, existing_library=existing,
            distance_meters=10,
        )

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=merged_candidate.pk),
        )

        unrelated.refresh_from_db()
        assert unrelated.disposition == DuplicateCandidate.PENDING
        assert unrelated.resolved_at is None

    def test_rejects_multi_select(self, admin_instance):
        """Selecting >1 candidate aborts without modifying anything."""
        c1 = _make_candidate()
        c2 = _make_candidate()

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk__in=[c1.pk, c2.pk]),
        )

        c1.refresh_from_db()
        c2.refresh_from_db()
        assert c1.disposition == DuplicateCandidate.PENDING
        assert c2.disposition == DuplicateCandidate.PENDING
        # Neither submitted library deactivated.
        assert c1.submitted_library.is_active is True
        assert c2.submitted_library.is_active is True

    def test_skips_already_resolved_candidate(self, admin_instance):
        """Selecting a single already-resolved candidate is a no-op with a warning."""
        candidate = _make_candidate()
        candidate.disposition = DuplicateCandidate.APPROVED_NEW
        candidate.resolved_at = timezone.now()
        candidate.save()

        admin_instance.merge_into_existing(
            _StubRequest(),
            DuplicateCandidate.objects.filter(pk=candidate.pk),
        )

        candidate.refresh_from_db()
        assert candidate.disposition == DuplicateCandidate.APPROVED_NEW
        # Submitted library not deactivated.
        assert candidate.submitted_library.is_active is True

    def test_atomicity(self, admin_instance, monkeypatch):
        """
        If something fails mid-merge, all writes must roll back.

        We force a failure at the StewardPartnership reassignment step by
        patching its ``objects.filter`` to raise. Earlier writes to Shelfie
        and IssueReport must roll back.
        """
        submitted = _make_library("Submitted")
        existing = _make_library("Existing", lng_offset=0.0001)
        shelfie = Shelfie.objects.create(
            library=submitted, photo="bookworm/shelfies/x",
        )
        report = IssueReport.objects.create(
            library=submitted, issue_type="wrong_location",
        )
        candidate = _make_candidate(submitted=submitted, existing=existing)

        # Patch StewardPartnership.objects.filter to raise mid-merge.
        original_filter = StewardPartnership.objects.filter
        def _boom(*args, **kwargs):
            raise RuntimeError("forced failure")
        monkeypatch.setattr(StewardPartnership.objects, "filter", _boom)

        with pytest.raises(RuntimeError):
            admin_instance.merge_into_existing(
                _StubRequest(),
                DuplicateCandidate.objects.filter(pk=candidate.pk),
            )

        # Restore so we can read.
        monkeypatch.setattr(StewardPartnership.objects, "filter", original_filter)

        shelfie.refresh_from_db()
        report.refresh_from_db()
        candidate.refresh_from_db()
        submitted.refresh_from_db()
        # Everything rolled back.
        assert shelfie.library_id == submitted.pk
        assert report.library_id == submitted.pk
        assert candidate.disposition == DuplicateCandidate.PENDING
        assert submitted.is_active is True
        assert submitted.merged_into is None
