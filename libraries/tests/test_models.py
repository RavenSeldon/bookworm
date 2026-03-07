"""
Tests for Bookworm models.

Covers: freshness tiers, slug generation, get_absolute_url,
shelfie creation signal, string representations.
"""

import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.geos import Point

from libraries.models import Library, Shelfie


# =============================================================================
# Freshness Status
# =============================================================================

class TestFreshnessStatus:
    def test_fresh_within_7_days(self, verified_library):
        """Libraries updated within 7 days are 'fresh'."""
        assert verified_library.freshness_status == "fresh"

    def test_stale_between_7_and_21_days(self, stale_library):
        """Libraries updated 7-21 days ago are 'stale'."""
        assert stale_library.freshness_status == "stale"

    def test_needs_visit_over_21_days(self, needs_visit_library):
        """Libraries updated over 21 days ago are 'needs_visit'."""
        assert needs_visit_library.freshness_status == "needs_visit"

    def test_freshness_color_mapping(self, verified_library, stale_library, needs_visit_library):
        """Each freshness tier maps to a distinct color."""
        assert verified_library.freshness_color == "#22c55e"
        assert stale_library.freshness_color == "#f59e0b"
        assert needs_visit_library.freshness_color == "#6b7280"


# =============================================================================
# Slug Generation
# =============================================================================

class TestSlugGeneration:
    def test_slug_generated_from_name(self, verified_library):
        """Named libraries get an auto-generated slug."""
        assert verified_library.slug == "oak-street-book-box"

    def test_slug_empty_when_unnamed(self, unnamed_library):
        """Unnamed libraries have an empty slug."""
        assert unnamed_library.slug == ""

    def test_slug_updates_on_rename(self, verified_library):
        """Slug updates when name changes."""
        verified_library.name = "New Name Here"
        verified_library.save()
        assert verified_library.slug == "new-name-here"

    def test_slug_handles_special_characters(self, db):
        """Slug strips special characters."""
        library = Library(
            name="Café & Books — Special!",
            location=Point(-123.1, 49.2, srid=4326),
            is_verified=True,
            is_active=True,
        )
        library.save()
        assert "cafe" in library.slug
        assert "&" not in library.slug


# =============================================================================
# get_absolute_url
# =============================================================================

class TestGetAbsoluteUrl:
    def test_named_library_uses_pk_slug_pattern(self, verified_library):
        """Named libraries get /library/<pk>-<slug>/ URLs."""
        url = verified_library.get_absolute_url()
        assert url == f"/library/{verified_library.pk}-oak-street-book-box/"

    def test_unnamed_library_uses_bare_pk(self, unnamed_library):
        """Unnamed libraries get /library/<pk>/ URLs."""
        url = unnamed_library.get_absolute_url()
        assert url == f"/library/{unnamed_library.pk}/"


# =============================================================================
# Shelfie Signal
# =============================================================================

class TestShelfieSignal:
    def test_creating_shelfie_updates_library_timestamp(self, verified_library):
        """Creating a shelfie updates the parent library's last_updated."""
        old_timestamp = verified_library.last_updated

        Shelfie.objects.create(
            library=verified_library,
            photo="bookworm/shelfies/signal_test",
        )

        verified_library.refresh_from_db()
        assert verified_library.last_updated > old_timestamp


# =============================================================================
# String Representations
# =============================================================================

class TestStringRepresentations:
    def test_named_library_str(self, verified_library):
        """Named library uses name as string."""
        assert str(verified_library) == "Oak Street Book Box"

    def test_unnamed_library_str(self, unnamed_library):
        """Unnamed library shows pk and coordinates."""
        s = str(unnamed_library)
        assert f"Library #{unnamed_library.pk}" in s

    def test_shelfie_str(self, shelfie):
        """Shelfie string includes library name and date."""
        s = str(shelfie)
        assert "Oak Street Book Box" in s

    def test_latest_shelfie_property(self, verified_library, shelfie):
        """latest_shelfie returns the most recent one."""
        assert verified_library.latest_shelfie == shelfie