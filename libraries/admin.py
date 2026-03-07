"""
Bookworm: Little Library Finder - Admin Configuration

Admin interface for managing libraries, shelfies, and issue reports.
Includes bulk actions and custom filters.
"""

from datetime import timedelta
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count

from .models import Library, Shelfie, IssueReport


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
    def mark_unresolpyved(self, request, queryset):
        updated = queryset.update(is_resolved=False)
        self.message_user(request, f"{updated} report(s) marked as unresolved.")