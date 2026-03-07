"""
Bookworm: Little Library Finder - Data Models

Models for managing Little Free Libraries, their photos (Shelfies), and issue reports.
Uses GeoDjango for spatial data handling with PostGIS backend.
"""

from django.contrib.gis.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
from cloudinary.models import CloudinaryField


class Library(models.Model):
    """
    Represents a Little Free Library location.

    Supports anonymous submissions with moderation workflow.
    Tracks freshness based on most recent Shelfie upload.
    """

    name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional friendly name, e.g., 'The Oak Street Book Box'"
    )
    description = models.TextField(
        blank=True,
        help_text="Accessibility notes, landmarks, special features"
    )
    location = models.PointField(
        srid=4326,  # WGS84 - standard GPS coordinate system
        help_text="Geographic coordinates of the library"
    )
    submitted_by_email = models.EmailField(
        blank=True,
        help_text="Optional contact for admin follow-up (not publicly displayed)"
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Approved by admin for public display"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="False for soft-deleted libraries (reported as non-existent)"
    )

    slug = models.SlugField(
        max_length=255,
        blank=True,
        help_text="Auto-generated from name for SEO-friendly URLS"
    )
    last_updated = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Auto-updated when a new Shelfie is added"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Libraries"
        ordering = ['-last_updated']
        indexes = [
            models.Index(fields=['is_verified', 'is_active']),
            models.Index(fields=['last_updated']),
        ]

    def __str__(self):
        if self.name:
            return self.name
        return f"Library #{self.pk} at ({self.location.y:.4f}, {self.location.x:.4f})"

    def save(self, *args, **kwargs):
        """Auto generate slug from name on save."""
        if self.name:
            self.slug = slugify(self.name)[:255]
        else:
            self.slug = ''
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """SEO-friendly URL using PK slug pattern"""
        from django.urls import reverse
        if self.slug:
            return reverse('libraries:library_detail', kwargs={
                'pk': self.pk,
                'slug': self.slug,
            })
        return reverse('libraries:library_detail_bare', kwargs={
            'pk': self.pk,
        })

    @property
    def freshness_status(self):
        """
        Determine freshness tier based on last_updated.

        Returns:
            str: 'fresh' (< 7 days), 'stale' (7-21 days), or 'needs_visit' (> 21 days)
        """
        now = timezone.now()
        age = now - self.last_updated

        if age < timedelta(days=7):
            return 'fresh'
        elif age < timedelta(days=21):
            return 'stale'
        return 'needs_visit'

    @property
    def freshness_color(self):
        """Map freshness status to display color."""
        colors = {
            'fresh': '#22c55e',  # Green
            'stale': '#f59e0b',  # Amber
            'needs_visit': '#6b7280'  # Grey
        }
        return colors.get(self.freshness_status, '#6b7280')

    @property
    def latest_shelfie(self):
        """Get the most recent Shelfie for this library."""
        return self.shelfies.order_by('-uploaded_at').first()

    def update_last_updated(self):
        """Refresh the last_updated timestamp."""
        self.last_updated = timezone.now()
        self.save(update_fields=['last_updated'])


class Shelfie(models.Model):
    """
    A photo of a library's current contents.

    Encourages community engagement by showing what books are available.
    Automatically updates parent library's freshness timestamp.
    """

    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name='shelfies'
    )
    photo = CloudinaryField(
        'image',
        folder='bookworm/shelfies',
        transformation={
            'quality': 'auto:good',
            'fetch_format': 'auto',
            'width': 1200,
            'height': 1200,
            'crop': 'limit'
        }
    )
    book_highlights = models.TextField(
        blank=True,
        help_text="Notable books spotted, e.g., 'Lots of kids books, some thrillers'"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Shelfie"
        verbose_name_plural = "Shelfies"

    def __str__(self):
        return f"Shelfie for {self.library} at {self.uploaded_at.strftime('%Y-%m-%d %H:%M')}"


@receiver(post_save, sender=Shelfie)
def update_library_timestamp(sender, instance, created, **kwargs):
    """
    Signal handler to update library's last_updated when a Shelfie is saved.

    Only triggers on creation to avoid infinite loops and unnecessary updates.
    """
    if created:
        instance.library.update_last_updated()


class IssueReport(models.Model):
    """
    User-submitted reports about problems with a library listing.

    Allows community to flag issues like wrong locations or removed libraries.
    """

    LIBRARY_ISSUE_CHOICES = [
        ('wrong_location', 'Wrong Location'),
        ('does_not_exist', "Doesn't Exist Anymore"),
        ('damaged', 'Damaged'),
        ('other', 'Other'),
    ]

    PHOTO_ISSUE_CHOICES = [
        ('inappropriate_photo', 'Inappropriate Content'),
        ('wrong_library', "Photo Doesn't Match This Library"),
        ('blurry_unreadable', 'Blurry or Unreadable'),
        ('other_photo', 'Other Photo Issue'),
    ]

    ISSUE_CHOICES = LIBRARY_ISSUE_CHOICES + PHOTO_ISSUE_CHOICES

    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name='issue_reports'
    )
    shelfie = models.ForeignKey(
        Shelfie,
        on_delete=models.CASCADE,
        related_name='issue_reports',
        null=True,
        blank=True,
        help_text="If reporting a specific photo, please link it here"
    )
    issue_type = models.CharField(
        max_length=20,
        choices=ISSUE_CHOICES,
        db_index=True
    )
    description = models.TextField(
        blank=True,
        help_text="Additional details about the issue"
    )
    reported_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Marked as resolved by admin"
    )

    class Meta:
        ordering = ['-reported_at']
        verbose_name = "Issue Report"

    def __str__(self):
        if self.shelfie:
            return f"{self.get_issue_type_display()} - Shelfie #{self.shelfie.pk} at {self.library}"
        return f"{self.get_issue_type_display()} - {self.library}"

    @property
    def is_photo_report(self):
        """Returns True if this report is about a specific shelfie."""
        return self.shelfie is not None

    @property
    def report_type(self):
        """Returns 'photo' or 'library' based on what's being reported."""
        return 'photo' if self.shelfie else 'library'