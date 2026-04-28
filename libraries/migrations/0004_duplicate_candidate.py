"""
Migration for Phase 3 (spatial duplicate flagging).

Adds:
  - Library.merged_into self-FK (audit pointer for soft-deleted duplicates).
  - DuplicateCandidate model + composite index on (disposition, -created_at).

Depends only on 0003 (the two 0002 siblings are already merged through it).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("libraries", "0003_stewardpartnership_scanevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="library",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "If this library was a duplicate that was merged into "
                    "another, this points at the surviving record. Set by "
                    "admin via the DuplicateCandidate merge action; combined "
                    "with is_active=False this row becomes a tombstone "
                    "preserving audit history."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="merged_from",
                to="libraries.library",
            ),
        ),
        migrations.CreateModel(
            name="DuplicateCandidate",
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
                    "distance_meters",
                    models.PositiveSmallIntegerField(
                        help_text=(
                            "Distance between the two libraries at "
                            "submission time, in metres."
                        ),
                    ),
                ),
                (
                    "disposition",
                    models.CharField(
                        choices=[
                            ("pending", "Pending review"),
                            ("approved_new", "Approved as new library"),
                            ("merged", "Merged into existing"),
                            ("rejected", "Rejected as junk"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "admin_notes",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Internal notes from the admin who reviewed "
                            "this candidate."
                        ),
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "resolved_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Set when the disposition leaves PENDING.",
                        null=True,
                    ),
                ),
                (
                    "submitted_library",
                    models.ForeignKey(
                        help_text=(
                            "The newly-submitted library that triggered the flag."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duplicate_candidates",
                        to="libraries.library",
                    ),
                ),
                (
                    "existing_library",
                    models.ForeignKey(
                        help_text=(
                            "The existing library that the submission is "
                            "suspected of duplicating."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duplicate_matches",
                        to="libraries.library",
                    ),
                ),
            ],
            options={
                "verbose_name": "Duplicate candidate",
                "verbose_name_plural": "Duplicate candidates",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="duplicatecandidate",
            index=models.Index(
                fields=["disposition", "-created_at"],
                name="libraries_d_disposi_a3c2f1_idx",
            ),
        ),
    ]
