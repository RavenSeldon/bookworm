"""
Tests for Phase 2 forms: StewardPartnershipForm.

Run with: pytest libraries/tests/test_phase2_forms.py -v
"""

import pytest

from libraries.forms import StewardPartnershipForm
from libraries.models import StewardPartnership


def _valid_payload(**overrides):
    """Helper — returns a payload that should pass validation."""
    base = {
        "library_address": "1234 Main St front lawn",
        "name": "Jane Doe",
        "contact": "jane@example.com",
        "sticker_interest": True,
        "hunt_interest": StewardPartnership.HUNT_INTEREST_YES,
        "hunt_message": "Welcome, fellow reader!",
        "website_url": "",  # honeypot — must be empty
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
class TestStewardPartnershipFormValidation:

    def test_valid_payload_passes(self):
        form = StewardPartnershipForm(data=_valid_payload())
        assert form.is_valid(), form.errors

    def test_missing_library_address_fails(self):
        form = StewardPartnershipForm(data=_valid_payload(library_address=""))
        assert not form.is_valid()
        assert "library_address" in form.errors

    def test_missing_contact_fails(self):
        form = StewardPartnershipForm(data=_valid_payload(contact=""))
        assert not form.is_valid()
        assert "contact" in form.errors

    def test_whitespace_only_contact_fails(self):
        """Bare spaces shouldn't satisfy the contact requirement."""
        form = StewardPartnershipForm(data=_valid_payload(contact="   "))
        assert not form.is_valid()
        assert "contact" in form.errors

    def test_name_is_optional(self):
        form = StewardPartnershipForm(data=_valid_payload(name=""))
        assert form.is_valid(), form.errors

    def test_hunt_message_is_optional(self):
        form = StewardPartnershipForm(data=_valid_payload(hunt_message=""))
        assert form.is_valid(), form.errors

    def test_hunt_message_max_length(self):
        """Anything over 140 chars is rejected (matches model field)."""
        too_long = "A" * 141
        form = StewardPartnershipForm(data=_valid_payload(hunt_message=too_long))
        assert not form.is_valid()
        assert "hunt_message" in form.errors

    def test_hunt_message_at_limit(self):
        """Exactly 140 chars is allowed."""
        at_limit = "A" * 140
        form = StewardPartnershipForm(data=_valid_payload(hunt_message=at_limit))
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestStewardPartnershipFormHoneypot:

    def test_filled_honeypot_fails_validation(self):
        """Bots filling the website_url field get rejected at form layer."""
        form = StewardPartnershipForm(
            data=_valid_payload(website_url="http://spam.example.com")
        )
        assert not form.is_valid()
        # The mixin raises a non-field-style error on website_url itself.
        assert "website_url" in form.errors


@pytest.mark.django_db
class TestStewardPartnershipEmptyConsentNudge:

    def test_no_sticker_no_hunt_emits_nonfield_warning(self):
        """
        Empty consent (no sticker AND hunt=no) should fail validation with
        a non-field error nudging the steward — not a hard model-level error.
        """
        form = StewardPartnershipForm(
            data=_valid_payload(
                sticker_interest=False,
                hunt_interest=StewardPartnership.HUNT_INTEREST_NO,
            )
        )
        assert not form.is_valid()
        assert form.non_field_errors()
        # The error mentions the polite-no concept.
        joined = " ".join(form.non_field_errors())
        assert "polite no" in joined.lower() or "no need to send" in joined.lower()

    def test_no_sticker_but_tell_me_more_passes(self):
        """Saying no to sticker but yes to learning more is a valid signal."""
        form = StewardPartnershipForm(
            data=_valid_payload(
                sticker_interest=False,
                hunt_interest=StewardPartnership.HUNT_INTEREST_TELL_ME_MORE,
            )
        )
        assert form.is_valid(), form.errors

    def test_sticker_yes_hunt_no_passes(self):
        """Sticker yes, Hunt no is a valid combination — no nudge."""
        form = StewardPartnershipForm(
            data=_valid_payload(
                sticker_interest=True,
                hunt_interest=StewardPartnership.HUNT_INTEREST_NO,
            )
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestStewardPartnershipFormSave:

    def test_save_creates_steward_partnership(self):
        form = StewardPartnershipForm(data=_valid_payload())
        assert form.is_valid()
        partnership = form.save()
        assert partnership.pk is not None
        assert partnership.sticker_interest is True
        assert partnership.hunt_interest == StewardPartnership.HUNT_INTEREST_YES
        assert partnership.library is None  # admin matches later
        assert partnership.is_processed is False
