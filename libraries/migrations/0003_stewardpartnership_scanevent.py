"""
Migration for Phase 2 (steward partnership + scan events).

Depends on both 0002 siblings to be safe — they can be applied in either
order, and this migration must run after both.
"""

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("libraries", "0002_issuereport_shelfie_alter_issuereport_issue_type"),
        ("libraries", "0002_library_slug"),
    ]

    operations = [
        migrations.CreateModel(
            name="StewardPartnership",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "library_address",
                    models.CharField(
                        help_text=(
                            "Address or descriptive location of the steward's library."
                        ),
                        max_length=300,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        help_text="Steward's name (optional).",
                        max_length=200,
                    ),
                ),
                (
                    "contact",
                    models.CharField(
                        help_text=(
                            "Email or phone number — we keep it private and use it only "
                            "to coordinate the sticker placement and the Library Hunt."
                        ),
                        max_length=200,
                    ),
                ),
                (
                    "sticker_interest",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Did the steward express interest in a Bookworm QR sticker on their library?"
                        ),
                    ),
                ),
                (
                    "hunt_interest",
                    models.CharField(
                        choices=[
                            ("yes", "Yes — count me in as a host stop"),
                            ("tell_me_more", "Tell me more before I decide"),
                            ("no", "Not interested in the Hunt"),
                        ],
                        default="no",
                        max_length=20,
                    ),
                ),
                (
                    "hunt_message",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Optional one-line message the steward wants visitors to see "
                            "during the Library Hunt."
                        ),
                        max_length=140,
                    ),
                ),
                (
                    "is_processed",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text=(
                            "Marks this consent as actioned (sticker placed, "
                            "hunt follow-up sent, etc.)."
                        ),
                    ),
                ),
                (
                    "admin_notes",
                    models.TextField(
                        blank=True,
                        help_text="Internal notes — not visible to the steward.",
                    ),
                ),
                (
                    "submitted_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "library",
                    models.ForeignKey(
                        blank=True,
                        help_text="Matched library record. Populated by admin after review.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="steward_partnerships",
                        to="libraries.library",
                    ),
                ),
            ],
            options={
                "verbose_name": "Steward partnership",
                "verbose_name_plural": "Steward partnerships",
                "ordering": ["-submitted_at"],
            },
        ),
        migrations.AddIndex(
            model_name="stewardpartnership",
            index=models.Index(
                fields=["is_processed", "-submitted_at"],
                name="libraries_s_is_proc_56b8a9_idx",
            ),
        ),
        migrations.CreateModel(
            name="ScanEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("matched", "Matched directly"),
                            ("picker_shown", "Picker shown for ambiguous match"),
                            ("picker_resolved", "Picker resolved to library"),
                            ("no_match", "No library within range"),
                            ("denied", "Geolocation denied by user"),
                            ("error", "Geolocation error or timeout"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "candidate_count",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text=(
                            "Number of libraries within the picker radius at scan time."
                        ),
                    ),
                ),
                (
                    "location",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True,
                        help_text=(
                            "Approximate scan location, rounded to ~11m precision."
                        ),
                        null=True,
                        srid=4326,
                    ),
                ),
                (
                    "accuracy_meters",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Browser-reported geolocation accuracy in meters.",
                        null=True,
                    ),
                ),
                (
                    "occurred_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "matched_library",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scan_events",
                        to="libraries.library",
                    ),
                ),
            ],
            options={
                "verbose_name": "Scan event",
                "verbose_name_plural": "Scan events",
                "ordering": ["-occurred_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scanevent",
            index=models.Index(
                fields=["outcome", "-occurred_at"],
                name="libraries_s_outcome_44c7b3_idx",
            ),
        ),
    ]
