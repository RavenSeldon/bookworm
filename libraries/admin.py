"""
Bookworm: Little Library Finder - Admin Configuration

Admin interface for managing libraries, shelfies, and issue reports.
Includes bulk actions and custom filters.
"""

import csv
from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.gis.admin import GISModelAdmin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count

from .models import (
    Library,
    Shelfie,
    IssueReport,
    StewardPartnership,
    ScanEvent,
    DuplicateCandidate,
    LibraryWalkRegistration,
)
from .emails import send_walk_broadcast


# =============================================================================
# Custom Filters
# =============================================================================

class FreshnessFilter(admin.SimpleListFilter):
    """Filter libraries by freshness status."""

    title = 'freshness'
    parameter_name = 'freshness'

    def lookups(self, request, model_admin):
        return [
            ('fresh', 'Fresh (< 7 days)'),
            ('stale', 'Stale (7-21 days)'),
            ('needs_visit', 'Needs Visit (> 21 days)'),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()

        if self.value() == 'fresh':
            return queryset.filter(last_updated__gte=now - timedelta(days=7))
        elif self.value() == 'stale':
            return queryset.filter(
                last_updated__lt=now - timedelta(days=7),
                last_updated__gte=now - timedelta(days=21)
            )
        elif self.value() == 'needs_visit':
            return queryset.filter(last_updated__lt=now - timedelta(days=21))
        return queryset


class HasIssuesFilter(admin.SimpleListFilter):
    """Filter libraries that have unresolved issues."""

    title = 'has issues'
    parameter_name = 'has_issues'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Has Unresolved Issues'),
            ('no', 'No Issues'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(issue_reports__is_resolved=False).distinct()
        elif self.value() == 'no':
            return queryset.exclude(issue_reports__is_resolved=False)
        return queryset


class HasPendingDuplicatesFilter(admin.SimpleListFilter):
    """Filter libraries that are flagged as potential duplicates pending review."""

    title = 'pending duplicate review'
    parameter_name = 'pending_dupes'

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Flagged as potential duplicate'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(
                duplicate_candidates__disposition=DuplicateCandidate.PENDING
            ).distinct()
        return queryset


# =============================================================================
# Inline Admins
# =============================================================================

class ShelfieInline(admin.TabularInline):
    """Inline display of Shelfies on Library detail page."""

    model = Shelfie
    extra = 0
    readonly_fields = ['photo_preview', 'uploaded_at']
    fields = ['photo_preview', 'photo', 'book_highlights', 'uploaded_at']
    ordering = ['-uploaded_at']

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-width: 150px; max-height: 100px; '
                'object-fit: cover; border-radius: 4px;" />',
                obj.photo.url
            )
        return "-"

    photo_preview.short_description = "Preview"


class IssueReportInline(admin.TabularInline):
    """Inline display of Issue Reports on Library detail page."""

    model = IssueReport
    extra = 0
    readonly_fields = ['reported_at']
    fields = ['issue_type', 'description', 'is_resolved', 'reported_at']
    ordering = ['-reported_at']


# =============================================================================
# Model Admins
# =============================================================================

@admin.register(Library)
class LibraryAdmin(GISModelAdmin):
    """Admin for Library model with map widget and approval actions."""

    list_display = [
        'name_display',
        'is_verified',
        'is_active',
        'freshness_badge',
        'shelfie_count',
        'location_display',
        'slug',
        'last_updated',
        'created_at',
    ]
    list_filter = [
        'is_verified',
        'is_active',
        FreshnessFilter,
        HasIssuesFilter,
        HasPendingDuplicatesFilter,
        'created_at',
    ]
    search_fields = ['name', 'description', 'submitted_by_email']
    readonly_fields = ['created_at', 'last_updated', 'freshness_badge', 'slug']
    inlines = [ShelfieInline, IssueReportInline]
    actions = ['approve_libraries', 'deactivate_libraries', 'reactivate_libraries']

    fieldsets = [
        (None, {
            'fields': ['name', 'description', 'location']
        }),
        ('Status', {
            'fields': ['is_verified', 'is_active', 'freshness_badge']
        }),
        ('Metadata', {
            'fields': ['submitted_by_email', 'created_at', 'last_updated'],
            'classes': ['collapse']
        }),
    ]

    # GIS map settings
    gis_widget_kwargs = {
        'attrs': {
            'default_lat': 49.2827,
            'default_lon': -123.1207,
            'default_zoom': 12,
        }
    }

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _shelfie_count=Count('shelfies')
        )

    def name_display(self, obj):
        return obj.name or f"Library #{obj.pk}"

    name_display.short_description = "Name"
    name_display.admin_order_field = 'name'

    def location_display(self, obj):
        if obj.location:
            return f"({obj.location.y:.4f}, {obj.location.x:.4f})"
        return "-"

    location_display.short_description = "Coordinates"

    def freshness_badge(self, obj):
        status = obj.freshness_status
        colors = {
            'fresh': '#22c55e',
            'stale': '#f59e0b',
            'needs_visit': '#6b7280'
        }
        labels = {
            'fresh': 'Fresh',
            'stale': 'Stale',
            'needs_visit': 'Needs Visit'
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            colors.get(status, '#6b7280'),
            labels.get(status, 'Unknown')
        )

    freshness_badge.short_description = "Freshness"

    def shelfie_count(self, obj):
        count = getattr(obj, '_shelfie_count', obj.shelfies.count())
        return count

    shelfie_count.short_description = "Shelfies"
    shelfie_count.admin_order_field = '_shelfie_count'

    # Admin Actions
    @admin.action(description="Approve selected libraries")
    def approve_libraries(self, request, queryset):
        updated = queryset.filter(is_verified=False).update(is_verified=True)
        self.message_user(request, f"{updated} library/libraries approved.")

    @admin.action(description="Deactivate selected libraries")
    def deactivate_libraries(self, request, queryset):
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"{updated} library/libraries deactivated.")

    @admin.action(description="Reactivate selected libraries")
    def reactivate_libraries(self, request, queryset):
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f"{updated} library/libraries reactivated.")


@admin.register(Shelfie)
class ShelfieAdmin(admin.ModelAdmin):
    """Admin for Shelfie model."""

    list_display = ['id', 'library_link', 'photo_preview', 'book_highlights_truncated', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['library__name', 'book_highlights']
    readonly_fields = ['uploaded_at', 'photo_preview_large']
    raw_id_fields = ['library']
    date_hierarchy = 'uploaded_at'

    def library_link(self, obj):
        url = reverse('admin:libraries_library_change', args=[obj.library.pk])
        return format_html('<a href="{}">{}</a>', url, obj.library)

    library_link.short_description = "Library"

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-width: 80px; max-height: 60px; '
                'object-fit: cover; border-radius: 4px;" />',
                obj.photo.url
            )
        return "-"

    photo_preview.short_description = "Photo"

    def photo_preview_large(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-width: 400px; max-height: 300px; '
                'border-radius: 8px;" />',
                obj.photo.url
            )
        return "-"

    photo_preview_large.short_description = "Photo Preview"

    def book_highlights_truncated(self, obj):
        if obj.book_highlights:
            return obj.book_highlights[:50] + ('...' if len(obj.book_highlights) > 50 else '')
        return "-"

    book_highlights_truncated.short_description = "Highlights"


@admin.register(IssueReport)
class IssueReportAdmin(admin.ModelAdmin):
    """Admin for Issue Reports with quick resolution."""

    list_display = [
        'id',
        'library_link',
        'issue_type',
        'description_truncated',
        'is_resolved',
        'reported_at'
    ]
    list_filter = ['issue_type', 'is_resolved', 'reported_at']
    search_fields = ['library__name', 'description']
    readonly_fields = ['reported_at']
    raw_id_fields = ['library']
    date_hierarchy = 'reported_at'
    actions = ['mark_resolved', 'mark_unresolved']

    def library_link(self, obj):
        url = reverse('admin:libraries_library_change', args=[obj.library.pk])
        return format_html('<a href="{}">{}</a>', url, obj.library)

    library_link.short_description = "Library"

    def description_truncated(self, obj):
        if obj.description:
            return obj.description[:75] + ('...' if len(obj.description) > 75 else '')
        return "-"

    description_truncated.short_description = "Description"

    @admin.action(description="Mark selected reports as resolved")
    def mark_resolved(self, request, queryset):
        updated = queryset.update(is_resolved=True)
        self.message_user(request, f"{updated} report(s) marked as resolved.")

    @admin.action(description="Mark selected reports as unresolved")
    def mark_unresolved(self, request, queryset):
        updated = queryset.update(is_resolved=False)
        self.message_user(request, f"{updated} report(s) marked as unresolved.")


@admin.register(StewardPartnership)
class StewardPartnershipAdmin(admin.ModelAdmin):
    list_display = (
        "library_address_short",
        "name",
        "sticker_interest",
        "hunt_interest_display_short",
        "library",
        "is_processed",
        "submitted_at",
    )
    list_filter = (
        "is_processed",
        "sticker_interest",
        "hunt_interest",
        "submitted_at",
    )
    search_fields = (
        "library_address",
        "name",
        "contact",
        "hunt_message",
        "admin_notes",
    )
    readonly_fields = ("submitted_at",)
    autocomplete_fields = ("library",)
    actions = ("mark_processed", "mark_unprocessed")

    fieldsets = (
        ("Steward submission", {
            "fields": (
                "library_address",
                "name",
                "contact",
                "submitted_at",
            ),
        }),
        ("Partnership", {
            "fields": (
                "sticker_interest",
                "hunt_interest",
                "hunt_message",
            ),
        }),
        ("Admin workflow", {
            "fields": (
                "library",
                "is_processed",
                "admin_notes",
            ),
        }),
    )

    @admin.display(description="Library address", ordering="library_address")
    def library_address_short(self, obj):
        if not obj.library_address:
            return "—"
        return (
            obj.library_address[:60] + "…"
            if len(obj.library_address) > 60
            else obj.library_address
        )

    @admin.display(description="Hunt", ordering="hunt_interest")
    def hunt_interest_display_short(self, obj):
        return obj.hunt_interest_display_short

    @admin.action(description="Mark selected as processed")
    def mark_processed(self, request, queryset):
        updated = queryset.update(is_processed=True)
        self.message_user(request, f"{updated} consent(s) marked as processed.")

    @admin.action(description="Mark selected as unprocessed")
    def mark_unprocessed(self, request, queryset):
        updated = queryset.update(is_processed=False)
        self.message_user(request, f"{updated} consent(s) marked as unprocessed.")


@admin.register(ScanEvent)
class ScanEventAdmin(admin.ModelAdmin):
    """
    Read-mostly analytics view. Admin can browse/filter scans but can't edit
    them (data integrity for the analytics).
    """

    list_display = (
        "occurred_at",
        "outcome",
        "matched_library",
        "candidate_count",
        "accuracy_meters",
    )
    list_filter = ("outcome", "occurred_at")
    search_fields = ("matched_library__name",)
    readonly_fields = (
        "outcome",
        "matched_library",
        "candidate_count",
        "location",
        "accuracy_meters",
        "occurred_at",
    )
    date_hierarchy = "occurred_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # View-only; existing records can be browsed but not edited.
        return False

    def has_delete_permission(self, request, obj=None):
        # Allow purging old scans for housekeeping.
        return True


# =============================================================================
# DuplicateCandidate Admin (Phase 3)
# =============================================================================

@admin.register(DuplicateCandidate)
class DuplicateCandidateAdmin(admin.ModelAdmin):
    """
    Side-by-side review of potential duplicate library submissions.

    Bulk actions cover the simple dispositions (approve as new / reject).
    The merge action lives separately (Phase 3 P2) because it has to
    reassign Shelfies, IssueReports, and StewardPartnerships in a
    transaction — not safe as an unconfirmed bulk action.
    """

    list_display = (
        "id",
        "submitted_link",
        "existing_link",
        "distance_meters",
        "disposition",
        "created_at",
    )
    list_filter = ("disposition", "created_at")
    search_fields = (
        "submitted_library__name",
        "existing_library__name",
        "admin_notes",
    )
    readonly_fields = (
        "submitted_library",
        "existing_library",
        "distance_meters",
        "created_at",
        "resolved_at",
        "side_by_side_view",
    )
    fieldsets = (
        ("Spatial match", {
            "fields": (
                "submitted_library",
                "existing_library",
                "distance_meters",
                "side_by_side_view",
            ),
        }),
        ("Admin disposition", {
            "fields": (
                "disposition",
                "admin_notes",
                "created_at",
                "resolved_at",
            ),
        }),
    )
    actions = ("approve_as_new", "merge_into_existing", "reject")
    date_hierarchy = "created_at"

    @admin.display(description="Submitted (new)", ordering="submitted_library")
    def submitted_link(self, obj):
        url = reverse(
            "admin:libraries_library_change", args=[obj.submitted_library_id]
        )
        return format_html('<a href="{}">#{} {}</a>',
                           url, obj.submitted_library_id,
                           obj.submitted_library.name or "(unnamed)")

    @admin.display(description="Existing", ordering="existing_library")
    def existing_link(self, obj):
        url = reverse(
            "admin:libraries_library_change", args=[obj.existing_library_id]
        )
        return format_html('<a href="{}">#{} {}</a>',
                           url, obj.existing_library_id,
                           obj.existing_library.name or "(unnamed)")

    @admin.display(description="Side-by-side comparison")
    def side_by_side_view(self, obj):
        """Render a compact comparison table for the change form."""
        def _photo(library):
            shelfie = library.latest_shelfie
            if shelfie and shelfie.photo:
                return format_html(
                    '<img src="{}" style="max-width: 280px; max-height: 200px; '
                    'object-fit: cover; border-radius: 4px;" />',
                    shelfie.photo.url,
                )
            return "(no shelfie)"

        def _coords(library):
            if library.location:
                return f"{library.location.y:.5f}, {library.location.x:.5f}"
            return "—"

        return format_html(
            '<table style="border-collapse: collapse; width: 100%;">'
            '<thead><tr>'
            '<th style="padding: 8px; text-align: left; border-bottom: 1px solid #ccc;">Submitted (new)</th>'
            '<th style="padding: 8px; text-align: left; border-bottom: 1px solid #ccc;">Existing</th>'
            '</tr></thead>'
            '<tbody><tr>'
            '<td style="padding: 8px; vertical-align: top; width: 50%;">'
            '<div><strong>{sub_name}</strong></div>'
            '<div style="color: #666; font-size: 12px;">#{sub_pk} · {sub_coords}</div>'
            '<div style="margin: 6px 0;">{sub_desc}</div>'
            '<div>{sub_photo}</div>'
            '</td>'
            '<td style="padding: 8px; vertical-align: top; width: 50%;">'
            '<div><strong>{ex_name}</strong></div>'
            '<div style="color: #666; font-size: 12px;">#{ex_pk} · {ex_coords}</div>'
            '<div style="margin: 6px 0;">{ex_desc}</div>'
            '<div>{ex_photo}</div>'
            '</td>'
            '</tr></tbody></table>',
            sub_name=obj.submitted_library.name or "(unnamed)",
            sub_pk=obj.submitted_library_id,
            sub_coords=_coords(obj.submitted_library),
            sub_desc=obj.submitted_library.description or "(no description)",
            sub_photo=_photo(obj.submitted_library),
            ex_name=obj.existing_library.name or "(unnamed)",
            ex_pk=obj.existing_library_id,
            ex_coords=_coords(obj.existing_library),
            ex_desc=obj.existing_library.description or "(no description)",
            ex_photo=_photo(obj.existing_library),
        )

    @admin.action(
        description="Merge submitted into existing (single selection only)"
    )
    def merge_into_existing(self, request, queryset):
        """
        Merge the submitted library into the existing one.

        Single-selection only — bulk merge would require per-row target
        selection, which doesn't fit Django's bulk-action model. Selecting
        multiple rows is rejected with an admin message.

        Merge rules (see CODEBASE.md ‘Phase 3 merge semantics’):
          - Existing library survives unchanged in identity.
          - Reassign FKs from submitted → existing for: Shelfie.library,
            IssueReport.library, StewardPartnership.library.
          - existing.last_updated = max(existing.last_updated,
            submitted.last_updated). Bulk reassignment doesn't fire the
            post_save signal, so we set this explicitly.
          - Submitted library: is_active=False, merged_into=existing.
            Preserves audit; the active-filter on public views naturally
            hides it.
          - This candidate: disposition=MERGED, resolved_at=now().
          - Auto-resolve sibling pending candidates: any other pending
            DuplicateCandidate rows whose submitted_library is the one
            being merged also get disposition=MERGED. Once the submission
            is merged into one survivor, parallel flags pointing at other
            existing libraries are moot.
        """
        pending = list(
            queryset.select_related(
                "submitted_library", "existing_library"
            ).filter(disposition=DuplicateCandidate.PENDING)
        )
        if len(pending) == 0:
            self.message_user(
                request,
                "No pending candidates selected. Merge only operates on "
                "PENDING candidates.",
                level=messages.WARNING,
            )
            return
        if len(pending) > 1:
            self.message_user(
                request,
                "Merge operates on a single candidate at a time. Select "
                "exactly one row and try again.",
                level=messages.ERROR,
            )
            return

        candidate = pending[0]
        self._perform_merge(candidate)
        self.message_user(
            request,
            f"Merged Library #{candidate.submitted_library_id} into "
            f"#{candidate.existing_library_id}. Submitted library "
            f"deactivated; FKs reassigned.",
            level=messages.SUCCESS,
        )

    @staticmethod
    def _perform_merge(candidate):
        """
        Execute the merge inside a single atomic transaction.

        Extracted as a staticmethod so tests can call it directly without
        going through the bulk-action wrapper.
        """
        submitted = candidate.submitted_library
        existing = candidate.existing_library
        now = timezone.now()

        with transaction.atomic():
            # 1. Reassign Shelfie.library. Bulk update — doesn't fire the
            #    post_save signal, which is what we want (we set
            #    last_updated explicitly below).
            Shelfie.objects.filter(library=submitted).update(library=existing)

            # 2. Reassign IssueReport.library. The shelfie FK on each report
            #    is preserved as-is — since we just moved that shelfie to
            #    `existing`, the report's shelfie pointer still resolves.
            IssueReport.objects.filter(library=submitted).update(
                library=existing
            )

            # 3. Reassign StewardPartnership.library — preserves admin's
            #    manual matches if any pointed at the soon-to-be-doomed row.
            StewardPartnership.objects.filter(library=submitted).update(
                library=existing
            )

            # 4. Promote existing.last_updated if the doomed row had a
            #    fresher shelfie. Use update() to skip Library.save()'s
            #    slug-overwrite side effect.
            new_last_updated = max(existing.last_updated, submitted.last_updated)
            if new_last_updated != existing.last_updated:
                Library.objects.filter(pk=existing.pk).update(
                    last_updated=new_last_updated
                )

            # 5. Soft-delete submitted with the audit pointer set.
            Library.objects.filter(pk=submitted.pk).update(
                is_active=False,
                merged_into=existing,
            )

            # 6. Mark this candidate resolved.
            candidate.disposition = DuplicateCandidate.MERGED
            candidate.resolved_at = now
            candidate.save(update_fields=["disposition", "resolved_at"])

            # 7. Auto-resolve sibling pending candidates pointing at the
            #    same submitted library — once it's merged, parallel flags
            #    are moot.
            DuplicateCandidate.objects.filter(
                submitted_library=submitted,
                disposition=DuplicateCandidate.PENDING,
            ).update(disposition=DuplicateCandidate.MERGED, resolved_at=now)

    @admin.action(description="Approve selected as new (clear flag)")
    def approve_as_new(self, request, queryset):
        """
        Mark candidate(s) as approved-new: the submitted library is genuinely
        a new library, not a duplicate. Clears the flag for admin.
        Does NOT touch is_verified — admin still verifies via the standard
        Library admin flow.
        """
        pending = queryset.filter(disposition=DuplicateCandidate.PENDING)
        updated = pending.update(
            disposition=DuplicateCandidate.APPROVED_NEW,
            resolved_at=timezone.now(),
        )
        self.message_user(
            request, f"{updated} candidate(s) approved as genuinely new."
        )

    @admin.action(description="Reject selected as junk (deactivate submitted library)")
    def reject(self, request, queryset):
        """
        Mark candidate(s) as rejected: the submitted library is not legitimate.
        Deactivates the submitted Library (soft-delete) and resolves the candidate.
        Existing libraries are untouched.
        """
        pending = queryset.select_related("submitted_library").filter(
            disposition=DuplicateCandidate.PENDING
        )
        count = 0
        for candidate in pending:
            # Soft-delete the submitted library and resolve the candidate.
            Library.objects.filter(pk=candidate.submitted_library_id).update(
                is_active=False
            )
            candidate.disposition = DuplicateCandidate.REJECTED
            candidate.resolved_at = timezone.now()
            candidate.save(update_fields=["disposition", "resolved_at"])
            count += 1
        self.message_user(
            request, f"{count} submission(s) rejected and deactivated."
        )


@admin.register(LibraryWalkRegistration)
class LibraryWalkRegistrationAdmin(admin.ModelAdmin):
    """
    Sign-ups for the Free Little Library Walk. Read-mostly; the CSV export
    action pulls the list for day-of planning (name tags, headcount,
    accessibility follow-ups). The email action messages selected registrants.
    """

    list_display = (
        "name",
        "email",
        "party_size",
        "needs_accessibility_followup",
        "submitted_at",
    )
    list_filter = ("needs_accessibility_followup", "submitted_at")
    search_fields = ("name", "email", "favourite_book", "accessibility_notes")
    readonly_fields = ("submitted_at",)
    date_hierarchy = "submitted_at"
    actions = ("export_as_csv", "email_registrants")

    @admin.action(description="Export selected registrations to CSV")
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="library_walk_registrations.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            "Name",
            "Email",
            "Party size",
            "Favourite book",
            "Accessibility notes",
            "Wants accessibility follow-up",
            "Submitted at",
        ])
        for reg in queryset:
            writer.writerow([
                reg.name,
                reg.email,
                reg.party_size,
                reg.favourite_book,
                reg.accessibility_notes,
                "Yes" if reg.needs_accessibility_followup else "No",
                reg.submitted_at.strftime("%Y-%m-%d %H:%M"),
            ])
        return response

    @admin.action(description="Email selected registrants")
    def email_registrants(self, request, queryset):
        if request.POST.get("apply"):
            subject = (request.POST.get("subject") or "").strip()
            body = (request.POST.get("message") or "").strip()
            if not subject or not body:
                self.message_user(
                    request,
                    "Subject and message are both required.",
                    level=messages.ERROR,
                )
            else:
                sent = send_walk_broadcast(queryset, subject, body)
                self.message_user(
                    request,
                    f"Sent {sent} email(s) to registrants.",
                    level=messages.SUCCESS,
                )
                return None
        context = {
            **self.admin_site.each_context(request),
            "title": "Email selected registrants",
            "registrations": queryset,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "selected": [str(pk) for pk in queryset.values_list("pk", flat=True)],
            "opts": self.model._meta,
        }
        return render(request, "admin/email_registrants.html", context)