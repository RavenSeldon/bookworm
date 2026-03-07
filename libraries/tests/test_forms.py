"""
Tests for Bookworm forms.

Covers: LibrarySubmissionForm validation, honeypot rejection,
ShelfieUploadForm, IssueReportForm (library vs photo context).
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from libraries.forms import LibrarySubmissionForm, ShelfieUploadForm, IssueReportForm
from libraries.models import IssueReport


@pytest.fixture
def valid_image():
    """A minimal valid JPEG for form tests."""
    from io import BytesIO
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile("test.jpg", buf.read(), content_type="image/jpeg")


# =============================================================================
# Library Submission Form
# =============================================================================

class TestLibrarySubmissionForm:
    def test_valid_submission(self, db, valid_image):
        """Form validates with location + photo."""
        form = LibrarySubmissionForm(
            data={
                "latitude": 49.2827,
                "longitude": -123.1207,
                "name": "Test Library",
                "description": "",
                "submitted_by_email": "",
                "book_highlights": "",
                "website_url": "",  # Honeypot empty
            },
            files={"photo": valid_image},
        )
        assert form.is_valid(), form.errors

    def test_missing_location_rejected(self, db, valid_image):
        """Form requires latitude and longitude."""
        form = LibrarySubmissionForm(
            data={
                "name": "No Location Library",
                "website_url": "",
            },
            files={"photo": valid_image},
        )
        assert not form.is_valid()
        assert "latitude" in form.errors or "__all__" in form.errors

    def test_missing_photo_rejected(self, db):
        """Form requires a photo."""
        form = LibrarySubmissionForm(
            data={
                "latitude": 49.2827,
                "longitude": -123.1207,
                "website_url": "",
            },
        )
        assert not form.is_valid()
        assert "photo" in form.errors

    def test_honeypot_rejects_bots(self, db, valid_image):
        """Filled honeypot field triggers rejection."""
        form = LibrarySubmissionForm(
            data={
                "latitude": 49.2827,
                "longitude": -123.1207,
                "website_url": "http://spam.com",  # Bot filled this
            },
            files={"photo": valid_image},
        )
        assert not form.is_valid()
        assert "website_url" in form.errors

    def test_name_is_optional(self, db, valid_image):
        """Library name is not required."""
        form = LibrarySubmissionForm(
            data={
                "latitude": 49.2827,
                "longitude": -123.1207,
                "name": "",
                "description": "",
                "submitted_by_email": "",
                "book_highlights": "",
                "website_url": "",
            },
            files={"photo": valid_image},
        )
        assert form.is_valid(), form.errors

    def test_save_creates_point_geometry(self, db, valid_image):
        """Saving the form creates a Library with a Point location."""
        form = LibrarySubmissionForm(
            data={
                "latitude": 49.2827,
                "longitude": -123.1207,
                "name": "Geo Test",
                "description": "",
                "submitted_by_email": "",
                "book_highlights": "",
                "website_url": "",
            },
            files={"photo": valid_image},
        )
        assert form.is_valid()
        library = form.save()
        assert library.location is not None
        assert abs(library.location.y - 49.2827) < 0.001
        assert abs(library.location.x - (-123.1207)) < 0.001
        assert library.is_verified is False  # Pending review


# =============================================================================
# Shelfie Upload Form
# =============================================================================

class TestShelfieUploadForm:
    def test_valid_upload(self, verified_library, valid_image):
        """Form validates with a photo."""
        form = ShelfieUploadForm(
            data={
                "book_highlights": "Some great books!",
                "website_url": "",
            },
            files={"photo": valid_image},
            library=verified_library,
        )
        assert form.is_valid(), form.errors

    def test_highlights_optional(self, verified_library, valid_image):
        """Book highlights are not required."""
        form = ShelfieUploadForm(
            data={
                "book_highlights": "",
                "website_url": "",
            },
            files={"photo": valid_image},
            library=verified_library,
        )
        assert form.is_valid(), form.errors

    def test_missing_photo_rejected(self, verified_library):
        """Form requires a photo."""
        form = ShelfieUploadForm(
            data={
                "book_highlights": "Books here",
                "website_url": "",
            },
            library=verified_library,
        )
        assert not form.is_valid()
        assert "photo" in form.errors


# =============================================================================
# Issue Report Form
# =============================================================================

class TestIssueReportForm:
    def test_library_report_valid(self, verified_library):
        """Library issue report with valid data."""
        form = IssueReportForm(
            data={
                "issue_type": "wrong_location",
                "description": "Moved to next block",
                "website_url": "",
            },
            library=verified_library,
        )
        assert form.is_valid(), form.errors

    def test_library_report_choices(self, verified_library):
        """Library reports show library-specific issue types."""
        form = IssueReportForm(library=verified_library)
        choice_values = [c[0] for c in form.fields["issue_type"].choices]
        assert "wrong_location" in choice_values
        assert "does_not_exist" in choice_values
        # Photo-specific choices should NOT be present
        assert "inappropriate_photo" not in choice_values

    def test_photo_report_choices(self, verified_library, shelfie):
        """Photo reports show photo-specific issue types."""
        form = IssueReportForm(library=verified_library, shelfie=shelfie)
        choice_values = [c[0] for c in form.fields["issue_type"].choices]
        assert "inappropriate_photo" in choice_values
        assert "blurry_unreadable" in choice_values
        # Library-specific choices should NOT be present
        assert "wrong_location" not in choice_values

    def test_missing_issue_type_rejected(self, verified_library):
        """Issue type is required."""
        form = IssueReportForm(
            data={
                "issue_type": "",
                "description": "Something wrong",
                "website_url": "",
            },
            library=verified_library,
        )
        assert not form.is_valid()
        assert "issue_type" in form.errors

    def test_description_optional(self, verified_library):
        """Description is not required."""
        form = IssueReportForm(
            data={
                "issue_type": "damaged",
                "description": "",
                "website_url": "",
            },
            library=verified_library,
        )
        assert form.is_valid(), form.errors