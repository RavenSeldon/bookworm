"""
Shared test fixtures for Bookworm tests.

Uses pytest-django fixtures with GeoDjango Point objects.
CloudinaryField is populated with a dummy string (stores resource ID in DB).
"""

import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.geos import Point

from libraries.models import Library, Shelfie, IssueReport


@pytest.fixture(autouse=True)
def simple_staticfiles(settings):
    """Use basic static files storage in tests (no manifest required)."""
    settings.STORAGES = {
        "default": settings.STORAGES.get("default", {}),
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }


@pytest.fixture
def verified_library(db):
    """A verified, active library with a slug."""
    library = Library(
        name="Oak Street Book Box",
        description="Next to the red mailbox",
        location=Point(-123.1207, 49.2827, srid=4326),  # Vancouver
        is_verified=True,
        is_active=True,
    )
    library.save()  # Triggers slug generation
    return library


@pytest.fixture
def unnamed_library(db):
    """A verified library with no name (empty slug)."""
    library = Library(
        name="",
        location=Point(-123.1000, 49.2500, srid=4326),
        is_verified=True,
        is_active=True,
    )
    library.save()
    return library


@pytest.fixture
def unverified_library(db):
    """An unverified library (pending review)."""
    library = Library(
        name="Pending Library",
        location=Point(-123.1100, 49.2600, srid=4326),
        is_verified=False,
        is_active=True,
    )
    library.save()
    return library


@pytest.fixture
def inactive_library(db):
    """A soft-deleted library."""
    library = Library(
        name="Removed Library",
        location=Point(-123.1300, 49.2700, srid=4326),
        is_verified=True,
        is_active=False,
    )
    library.save()
    return library


@pytest.fixture
def shelfie(db, verified_library):
    """A shelfie attached to the verified library."""
    return Shelfie.objects.create(
        library=verified_library,
        photo="bookworm/shelfies/test_photo",  # CloudinaryField stores a string
        book_highlights="Great kids books today!",
    )


@pytest.fixture
def stale_library(db):
    """A library last updated 14 days ago (stale freshness)."""
    library = Library(
        name="Stale Library",
        location=Point(-123.1400, 49.2900, srid=4326),
        is_verified=True,
        is_active=True,
        last_updated=timezone.now() - timedelta(days=14),
    )
    library.save()
    return library


@pytest.fixture
def needs_visit_library(db):
    """A library last updated 30 days ago (needs_visit freshness)."""
    library = Library(
        name="Old Library",
        location=Point(-123.1500, 49.3000, srid=4326),
        is_verified=True,
        is_active=True,
        last_updated=timezone.now() - timedelta(days=30),
    )
    library.save()
    return library


@pytest.fixture
def issue_report(db, verified_library):
    """An issue report for the verified library."""
    return IssueReport.objects.create(
        library=verified_library,
        issue_type="wrong_location",
        description="It moved to the next block",
    )


@pytest.fixture
def sample_image():
    """A minimal valid JPEG for form upload tests."""
    from io import BytesIO
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile("test.jpg", buf.read(), content_type="image/jpeg")