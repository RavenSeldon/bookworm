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
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_from",
        help_text=(
            "If this library was a duplicate that was merged into another, "
            "this points at the surviving record. Set by admin via the "
            "DuplicateCandidate merge action; combined with is_active=False "
            "this row becomes a tombstone preserving audit history."
        ),
    )

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


class StewardPartnership(models.Model):
    """
    A Little Free Library steward's response to the Bookworm consent ask.

    Stewards receive a hand-delivered envelope with an info sheet + consent
    card. They can respond by scanning the QR on the card to open this form,
    or emailing the project lead. This model captures the digital and the
    manually-transcribed (by admin) responses.

    Note: stewards may submit before their library has been added to Bookworm,
    so `library` is nullable. Admin matches the consent to a Library record
    later via the admin "match" action.
    """

    HUNT_INTEREST_YES = "yes"
    HUNT_INTEREST_TELL_ME_MORE = "tell_me_more"
    HUNT_INTEREST_NO = "no"
    HUNT_INTEREST_CHOICES = [
        (HUNT_INTEREST_YES, "Yes — count me in as a host stop"),
        (HUNT_INTEREST_TELL_ME_MORE, "Tell me more before I decide"),
        (HUNT_INTEREST_NO, "Not interested in the Hunt"),
    ]

    # What the steward tells us
    library_address = models.CharField(
        max_length=300,
        help_text="Address or descriptive location of the steward's library.",
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Steward's name (optional).",
    )
    contact = models.CharField(
        max_length=200,
        help_text="Email or phone number — we keep it private and use it only "
                  "to coordinate the sticker placement and the Library Hunt.",
    )
    sticker_interest = models.BooleanField(
        default=False,
        help_text="Did the steward partner and ask for a Bookworm QR sticker on their library?",
    )
    hunt_interest = models.CharField(
        max_length=20,
        choices=HUNT_INTEREST_CHOICES,
        default=HUNT_INTEREST_NO,
    )
    hunt_message = models.CharField(
        max_length=140,
        blank=True,
        help_text="Optional one-line message the steward wants visitors to see "
                  "during the Library Hunt.",
    )

    # Admin workflow
    library = models.ForeignKey(
        "Library",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="steward_partnerships",
        help_text="Matched library record. Populated by admin after review.",
    )
    is_processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Marks this consent as actioned (sticker placed, hunt follow-up sent, etc.).",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes — not visible to the steward.",
    )

    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Steward Partnership"
        verbose_name_plural = "Steward Partnerships"
        indexes = [
            models.Index(fields=["is_processed", "-submitted_at"]),
        ]

    def __str__(self):
        bits = [self.library_address[:60]]
        if self.name:
            bits.append(f"({self.name})")
        return " ".join(bits)

    @property
    def hunt_interest_display_short(self):
        """Concise label for admin list_display."""
        return {
            self.HUNT_INTEREST_YES: "Yes",
            self.HUNT_INTEREST_TELL_ME_MORE: "Tell me more",
            self.HUNT_INTEREST_NO: "No",
        }.get(self.hunt_interest, "—")


class ScanEvent(models.Model):
    """
    A single QR-sticker scan, recorded for analytics.
      - tune the picker thresholds based on real distance distributions
      - find missing libraries (zero-match scans cluster around real LFLs)
      - measure the funnel — scans → matched library → shelfie added

    Privacy: no IP, no user agent. Coordinates are rounded to 4 decimals
    (~11m precision) before storage. Enough for cluster analysis, not enough
    to retrace an individual user's path.
    """

    OUTCOME_MATCHED = "matched"
    OUTCOME_PICKER_SHOWN = "picker_shown"
    OUTCOME_PICKER_RESOLVED = "picker_resolved"
    OUTCOME_NO_MATCH = "no_match"
    OUTCOME_DENIED = "denied"
    OUTCOME_ERROR = "error"
    OUTCOME_CHOICES = [
        (OUTCOME_MATCHED, "Matched directly"),
        (OUTCOME_PICKER_SHOWN, "Picker shown for ambiguous match"),
        (OUTCOME_PICKER_RESOLVED, "Picker resolved to library"),
        (OUTCOME_NO_MATCH, "No library within range"),
        (OUTCOME_DENIED, "Geolocation denied by user"),
        (OUTCOME_ERROR, "Geolocation error or timeout"),
    ]

    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        db_index=True,
    )
    matched_library = models.ForeignKey(
        "Library",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_events",
    )
    candidate_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of libraries within the picker radius at scan time.",
    )

    # Approximate location — rounded to 4 decimal places (~11m) for privacy.
    # See _round_point() in views.
    location = models.PointField(
        srid=4326,
        null=True,
        blank=True,
        help_text="Approximate scan location, rounded to ~11m precision.",
    )
    accuracy_meters = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Browser-reported geolocation accuracy in meters.",
    )

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "Scan event"
        verbose_name_plural = "Scan events"
        indexes = [
            models.Index(fields=["outcome", "-occurred_at"]),
        ]

    def __str__(self):
        return f"{self.get_outcome_display()} @ {self.occurred_at:%Y-%m-%d %H:%M}"


class DuplicateCandidate(models.Model):
    """
    Records a spatial proximity match between a newly-submitted Library and
    an existing one. Created at submission time when a new library lands
    within ``DUPLICATE_PROXIMITY_RADIUS_M`` of an existing active library.

    Never blocks the submission. The submitter sees the standard success
    page; admin gains a review surface to decide whether the new submission
    is genuinely new, a duplicate to merge, or junk to reject.

    Storage rationale (vs putting a single FK on Library):
      - One submission can produce multiple candidates (apartment-complex
        case where 2-3 existing libraries cluster within radius).
      - Disposition history persists past resolution — useful for tuning
        the proximity threshold once we have data.
      - The candidate row is identity-agnostic by design: it records the
        spatial relationship, not who submitted. The future trust-tier
        system can layer on top without schema churn.
    """

    PENDING = "pending"
    APPROVED_NEW = "approved_new"
    MERGED = "merged"
    REJECTED = "rejected"
    DISPOSITION_CHOICES = [
        (PENDING, "Pending review"),
        (APPROVED_NEW, "Approved as new library"),
        (MERGED, "Merged into existing"),
        (REJECTED, "Rejected as junk"),
    ]

    submitted_library = models.ForeignKey(
        "Library",
        on_delete=models.CASCADE,
        related_name="duplicate_candidates",
        help_text="The newly-submitted library that triggered the flag.",
    )
    existing_library = models.ForeignKey(
        "Library",
        on_delete=models.CASCADE,
        related_name="duplicate_matches",
        help_text="The existing library that the submission is suspected of duplicating.",
    )
    distance_meters = models.PositiveSmallIntegerField(
        help_text="Distance between the two libraries at submission time, in metres.",
    )
    disposition = models.CharField(
        max_length=20,
        choices=DISPOSITION_CHOICES,
        default=PENDING,
        db_index=True,
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes from the admin who reviewed this candidate.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the disposition leaves PENDING.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Duplicate candidate"
        verbose_name_plural = "Duplicate candidates"
        indexes = [
            models.Index(fields=["disposition", "-created_at"]),
        ]

    def __str__(self):
        return (
            f"#{self.submitted_library_id} ~ #{self.existing_library_id} "
            f"({self.distance_meters}m, {self.get_disposition_display()})"
        )

    @property
    def is_pending(self):
        return self.disposition == self.PENDING


class LibraryWalkRegistration(models.Model):
    """
    A sign-up for the Free Little Library Walk (Sunday, August 16, 2026).

    Optional and lightweight -- registering helps us plan, but walk-ups are
    welcome. No outbound email is required; an admin notification fires only
    if ADMIN_EMAIL is configured (fail-silent), matching the submission and
    partnership flows.
    """

    name = models.CharField(
        max_length=120,
        help_text="We'll put this on your name tag.",
    )
    email = models.EmailField(
        help_text=(
            "Only used to reach you about this walk -- e.g. if heat or timing "
            "forces a change. We won't add you to any list."
        ),
    )
    party_size = models.PositiveSmallIntegerField(
        default=1,
        help_text="Including you. A rough number is fine -- it helps us plan.",
    )
    favourite_book = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional. Goes on your name tag as a conversation starter.",
    )
    accessibility_notes = models.TextField(
        blank=True,
        help_text=(
            "Tell us about any accessibility needs and we'll reach out "
            "personally to make the day work for you."
        ),
    )
    needs_accessibility_followup = models.BooleanField(
        default=False,
        help_text="I'd like someone to follow up with me about accessibility.",
    )
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Library Walk registration"
        verbose_name_plural = "Library Walk registrations"

    def __str__(self):
        return f"{self.name} (party of {self.party_size}) -- {self.submitted_at:%Y-%m-%d}"