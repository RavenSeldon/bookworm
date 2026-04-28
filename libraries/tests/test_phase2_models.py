"""
Tests for Phase 2 models: StewardPartnership and ScanEvent.

Run with: pytest libraries/tests/test_phase2_models.py -v
"""

import pytest
from django.contrib.gis.geos import Point

from libraries.models import Library, ScanEvent, StewardPartnership


@pytest.mark.django_db

class TestStewardPartnership:

    def test_creation_with_minimum_fields(self):
        """StewardPartnership saves with the minimum required fields."""
        partnership = StewardPartnership.objects.create(
            library_address="1234 Main St",
            contact="steward@example.com",
        )
        assert partnership.pk is not None
        assert partnership.sticker_interest is False
        assert partnership.hunt_interest == StewardPartnership.HUNT_INTEREST_NO
        assert partnership.is_processed is False
        assert partnership.submitted_at is not None

    def test_str_uses_address_and_name(self):
        """__str__ includes the address and (when present) the name."""
        c1 = StewardPartnership.objects.create(
            library_address="The Hemlock corner library",
            name="Jane",
            contact="jane@example.com",
        )
        assert "Hemlock" in str(c1)
        assert "(Jane)" in str(c1)

        c2 = StewardPartnership.objects.create(
            library_address="The Hemlock corner library",
            contact="jane@example.com",
        )
        assert "Hemlock" in str(c2)
        assert "(" not in str(c2)  # no name parens when name is blank

    def test_str_truncates_long_address(self):
        """__str__ caps the address segment at 60 chars."""
        long_addr = "A" * 100
        c = StewardPartnership.objects.create(
            library_address=long_addr,
            contact="x@example.com",
        )
        # The first 60 chars of the address should appear in str(); the
        # full 100 should not.
        assert "A" * 60 in str(c)
        assert "A" * 80 not in str(c)

    def test_hunt_interest_display_short(self):
        """The short-display property maps each choice correctly."""
        cases = [
            (StewardPartnership.HUNT_INTEREST_YES, "Yes"),
            (StewardPartnership.HUNT_INTEREST_TELL_ME_MORE, "Tell me more"),
            (StewardPartnership.HUNT_INTEREST_NO, "No"),
        ]
        for value, expected in cases:
            c = StewardPartnership.objects.create(
                library_address="x",
                contact="x@example.com",
                hunt_interest=value,
            )
            assert c.hunt_interest_display_short == expected

    def test_library_fk_is_nullable(self):
        """Partnerships can exist without a matched Library."""
        c = StewardPartnership.objects.create(
            library_address="Unmatched library somewhere",
            contact="x@example.com",
        )
        assert c.library is None

    def test_library_fk_link(self, verified_library):
        """When matched, the FK and reverse relation work."""
        c = StewardPartnership.objects.create(
            library_address="Matched library",
            contact="x@example.com",
            library=verified_library,
        )
        assert c.library == verified_library
        assert c in verified_library.steward_partnerships.all()

    def test_library_deletion_sets_null(self, verified_library):
        """on_delete=SET_NULL preserves the partnership record if the library is removed."""
        c = StewardPartnership.objects.create(
            library_address="Matched library",
            contact="x@example.com",
            library=verified_library,
        )
        verified_library.delete()
        c.refresh_from_db()
        assert c.library is None

    def test_ordering_is_newest_first(self):
        """Default ordering surfaces the most recent submissions first."""
        old = StewardPartnership.objects.create(
            library_address="old", contact="a@example.com"
        )
        new = StewardPartnership.objects.create(
            library_address="new", contact="b@example.com"
        )
        ordered = list(StewardPartnership.objects.all())
        assert ordered.index(new) < ordered.index(old)


@pytest.mark.django_db
class TestScanEvent:

    def test_creation_with_minimum_fields(self):
        """ScanEvent saves with just an outcome."""
        event = ScanEvent.objects.create(
            outcome=ScanEvent.OUTCOME_DENIED,
        )
        assert event.pk is not None
        assert event.matched_library is None
        assert event.candidate_count == 0
        assert event.location is None

    def test_str_includes_outcome_and_timestamp(self):
        event = ScanEvent.objects.create(
            outcome=ScanEvent.OUTCOME_NO_MATCH,
        )
        as_str = str(event)
        # The display label appears (not the raw choice key).
        assert "No library within range" in as_str

    def test_matched_library_relationship(self, verified_library):
        event = ScanEvent.objects.create(
            outcome=ScanEvent.OUTCOME_MATCHED,
            matched_library=verified_library,
        )
        assert event.matched_library == verified_library
        assert event in verified_library.scan_events.all()

    def test_library_deletion_sets_null(self, verified_library):
        """Deleting a library preserves scan history with library=NULL."""
        event = ScanEvent.objects.create(
            outcome=ScanEvent.OUTCOME_MATCHED,
            matched_library=verified_library,
        )
        verified_library.delete()
        event.refresh_from_db()
        assert event.matched_library is None
        # Outcome is preserved for analytics.
        assert event.outcome == ScanEvent.OUTCOME_MATCHED

    def test_location_field_stores_point(self):
        """The PointField round-trips via PostGIS."""
        # Vancouver-ish.
        p = Point(-123.10, 49.26, srid=4326)
        event = ScanEvent.objects.create(
            outcome=ScanEvent.OUTCOME_MATCHED,
            location=p,
        )
        event.refresh_from_db()
        assert event.location is not None
        assert event.location.srid == 4326
        # Same coords (PostGIS may normalise but to the precision we care
        # about, identity holds).
        assert abs(event.location.x - p.x) < 1e-6
        assert abs(event.location.y - p.y) < 1e-6

    def test_outcome_choices_are_enforceable(self):
        """All declared outcome constants are valid choice keys."""
        valid_outcomes = {
            ScanEvent.OUTCOME_MATCHED,
            ScanEvent.OUTCOME_PICKER_SHOWN,
            ScanEvent.OUTCOME_PICKER_RESOLVED,
            ScanEvent.OUTCOME_NO_MATCH,
            ScanEvent.OUTCOME_DENIED,
            ScanEvent.OUTCOME_ERROR,
        }
        choice_keys = {key for key, _ in ScanEvent.OUTCOME_CHOICES}
        assert valid_outcomes == choice_keys

    def test_ordering_is_newest_first(self):
        old = ScanEvent.objects.create(outcome=ScanEvent.OUTCOME_DENIED)
        new = ScanEvent.objects.create(outcome=ScanEvent.OUTCOME_MATCHED)
        ordered = list(ScanEvent.objects.all())
        assert ordered.index(new) < ordered.index(old)