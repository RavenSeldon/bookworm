"""
Migration: Add slug field to Library model

Adds a slug field and populates it from existing library names.

"""

from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    """Generate slugs for all existing libraries."""
    Library = apps.get_model('libraries', 'Library')
    for library in Library.objects.all():
        if library.name:
            library.slug = slugify(library.name)[:255]
            library.save(update_fields=['slug'])


def reverse_slugs(apps, schema_editor):
    """Reverse: clear all slugs."""
    Library = apps.get_model('libraries', 'Library')
    Library.objects.all().update(slug='')


class Migration(migrations.Migration):

    dependencies = [
        ('libraries', '0002_issuereport_shelfie_alter_issuereport_issue_type')
    ]

    operations = [
        # Add the slug field (blank=True so existing rows are fine)
        migrations.AddField(
            model_name='library',
            name='slug',
            field=models.SlugField(
                blank=True,
                help_text='Auto-generated from name for SEO-friendly URLs',
                max_length=255,
            ),
        ),
        # Populate slugs from existing names
        migrations.RunPython(populate_slugs, reverse_slugs),
    ]
