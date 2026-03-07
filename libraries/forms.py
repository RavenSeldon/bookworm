"""
Bookworm: Little Library Finder - Forms
-library submissions
-Shelfie uploads
-issue reports
-includes honeypot spam prevention for anonymous submissions.
"""

from django import forms
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from .models import Library, Shelfie, IssueReport


class HoneypotMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add honeypot field - hidden from humans via CSS
        self.fields["website_url"] = forms.CharField(
            required=False,
            widget=forms.TextInput(
                attrs={
                    "class": "hp-field",  # Invisible styling
                    "tabindex": "-1",
                    "autocomplete": "off",
                    "aria-hidden": "true",
                }
            ),
            label="Leave this field empty",
        )

    def clean_website_url(self):
        """Reject form if honeypot field is filled."""
        value = self.cleaned_data.get("website_url", "")
        if value:
            raise ValidationError(
                "Form submission rejected.", code="honeypot_triggered"
            )
        return value


class LibrarySubmissionForm(HoneypotMixin, forms.ModelForm):
    """
    Form for submitting a new library location.

    Requires initial photo (Shelfie) to ensure quality submissions.
    Location is captured via map click or geolocation.
    """

    # Location fields (populated by JavaScript)
    latitude = forms.FloatField(widget=forms.HiddenInput(), min_value=-90, max_value=90)
    longitude = forms.FloatField(
        widget=forms.HiddenInput(), min_value=-180, max_value=180
    )

    # Initial Shelfie fields
    photo = forms.ImageField(
        required=True,
        help_text="Take a photo of the library's current contents",
        widget=forms.FileInput(
            attrs={
                "accept": "image/*",
                "capture": "environment",  # Opens camera on mobile
                "class": "form-control",
            }
        ),
    )
    book_highlights = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control",
                "placeholder": "What books did you spot? e.g., Romance novels, travel books, some mysteries'",
            }
        ),
    )

    class Meta:
        model = Library
        fields = ["name", "description", "submitted_by_email"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "[Optional] Give it a friendly name :)",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Accessibility notes, nearby landmarks, special features...",
                }
            ),
            "submitted_by_email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "[Optional] Your email",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        lat = cleaned_data.get("latitude")
        lng = cleaned_data.get("longitude")

        if lat is None or lng is None:
            raise ValidationError(
                "Please select a location on the map or use your current location.",
                code="location_required",
            )

        return cleaned_data

    def save(self, commit=True):
        """Create library with Point geometry from lat/lng."""
        library = super().save(commit=False)

        # Create Point from coordinates (Point takes lng, lat order)
        library.location = Point(
            self.cleaned_data["longitude"], self.cleaned_data["latitude"], srid=4326
        )
        library.is_verified = False  # Requires admin approval

        if commit:
            library.save()

        return library


class ShelfieUploadForm(HoneypotMixin, forms.ModelForm):
    """
    Form for uploading a new Shelfie to an existing library.

    Simplified form for quick updates.
    Updates to verified libraries are auto-approved.
    """

    class Meta:
        model = Shelfie
        fields = ["photo", "book_highlights"]
        widgets = {
            "photo": forms.FileInput(
                attrs={
                    "accept": "image/*",
                    "capture": "environment",
                    "class": "form-control",
                    "required": True,
                }
            ),
            "book_highlights": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "What books are available? e.g., 'Fresh batch of books for kids!'",
                }
            ),
        }

    def __init__(self, *args, library=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.library = library

    def save(self, commit=True):
        shelfie = super().save(commit=False)
        if self.library:
            shelfie.library = self.library
        if commit:
            shelfie.save()
        return shelfie


class IssueReportForm(HoneypotMixin, forms.ModelForm):
    """
    Form for reporting issues with a library listing.

    Allows community members to flag problems for admin review.
    """

    class Meta:
        model = IssueReport
        fields = ["issue_type", "description"]
        widgets = {
            "issue_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Provide any additional details that might help...",
                }
            ),
        }

    def __init__(self, *args, library=None, shelfie=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.library = library
        self.shelfie = shelfie

        # User appropriate choices based on report type
        if shelfie:
            # Photo report - show photo specific issues
            self.fields["issue_type"].choices = IssueReport.PHOTO_ISSUE_CHOICES
            self.fields["description"].widget.attrs["placeholder"] = (
                "Describe the issue with this photo..."
            )

        else:
            # Library report - show library-specific issues
            self.fields["issue_type"].choices = IssueReport.LIBRARY_ISSUE_CHOICES
            self.fields["description"].widget.attrs["placeholder"] = (
                "Provide any additional details that might help..."
            )

    def save(self, commit=True):
        report = super().save(commit=False)
        if self.library:
            report.library = self.library
        if self.shelfie:
            report.shelfie = self.shelfie
        if commit:
            report.save()
        return report
