"""Tests for outbound email: helper, admin broadcast action, management commands.

All sends go to Django's locmem backend (pinned in ``email_settings`` below), so
no real mail is sent and Resend is never contacted.

These tests use a local ``outbox`` fixture instead of pytest-django's
``mailoutbox``. pytest-django resets ``django.core.mail.outbox`` to a fresh list
while setting up the ``db`` fixture; an outbox captured *before* db setup points
at the stale list and never sees the sent messages. ``outbox`` depends on ``db``,
so it is always captured after that reset and reflects what was actually sent.
"""

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse

from libraries.emails import send_email, send_walk_broadcast, WALK_BROADCAST_FOOTER
from libraries.models import LibraryWalkRegistration


@pytest.fixture
def outbox(db):
    """A live, empty mail.outbox captured after db setup. See module docstring."""
    mail.outbox = []
    return mail.outbox


@pytest.fixture
def registrations(db):
    return [
        LibraryWalkRegistration.objects.create(
            name="Ada", email="ada@example.com", party_size=2,
        ),
        LibraryWalkRegistration.objects.create(
            name="", email="anon@example.com", party_size=1,
        ),
    ]


@pytest.fixture(autouse=True)
def email_settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "Bookworm <hello@bookworm.guide>"
    settings.EMAIL_REPLY_TO = "hello@bookworm.guide"
    settings.ADMIN_EMAIL = "admin@example.com"


def test_send_email_sets_from_reply_to_and_html(outbox, settings):
    settings.DEFAULT_FROM_EMAIL = "Bookworm <ben@bookworm.guide>"
    settings.EMAIL_REPLY_TO = "ben@bookworm.guide"

    sent = send_email(
        subject="Hello",
        to="someone@example.com",
        text_body="plain body",
        html_body="<p>html body</p>",
    )

    assert sent == 1
    assert len(outbox) == 1
    msg = outbox[0]
    assert msg.subject == "Hello"
    assert msg.from_email == "Bookworm <ben@bookworm.guide>"
    assert msg.to == ["someone@example.com"]
    assert msg.reply_to == ["ben@bookworm.guide"]
    assert msg.body == "plain body"
    assert msg.alternatives == [("<p>html body</p>", "text/html")]


def test_send_email_accepts_string_or_list(outbox):
    send_email("S", ["a@example.com", "b@example.com"], "body")
    assert outbox[0].to == ["a@example.com", "b@example.com"]


def test_walk_broadcast_one_message_per_recipient(outbox, settings, registrations):
    settings.EMAIL_REPLY_TO = "ben@bookworm.guide"

    sent = send_walk_broadcast(registrations, "Update", "See you Sunday.")

    assert sent == 2
    assert len(outbox) == 2
    for msg in outbox:
        assert len(msg.to) == 1
        assert msg.reply_to == ["ben@bookworm.guide"]
        assert WALK_BROADCAST_FOOTER in msg.body
        assert msg.alternatives

    bodies = "\n".join(m.body for m in outbox)
    assert "Hi Ada," in bodies
    assert "Hi,\n" in bodies


def test_walk_broadcast_dry_run_sends_nothing(outbox, registrations):
    sent = send_walk_broadcast(registrations, "Update", "body", dry_run=True)
    assert sent == 2
    assert outbox == []


def test_admin_notification_on_walk_registration(client, settings, outbox):
    cache.clear()
    settings.ADMIN_EMAIL = "admin@example.com"

    assert client.get("/library-walk/").status_code == 200

    resp = client.post(
        "/library-walk/register/",
        {
            "name": "Reg Tester",
            "email": "reg@example.com",
            "party_size": "3",
            "_form_loaded_at": "0",
        },
    )

    assert resp.status_code == 302
    assert LibraryWalkRegistration.objects.count() == 1
    assert len(outbox) == 1
    assert outbox[0].to == ["admin@example.com"]
    assert "Library Walk registration" in outbox[0].subject


def test_admin_email_action_sends(admin_client, outbox, registrations):
    url = reverse("admin:libraries_librarywalkregistration_changelist")
    resp = admin_client.post(
        url,
        {
            "action": "email_registrants",
            ACTION_CHECKBOX_NAME: [str(r.pk) for r in registrations],
            "apply": "1",
            "subject": "Walk update",
            "message": "See you Sunday!",
        },
    )

    assert resp.status_code in (200, 302)
    assert len(outbox) == 2
    for msg in outbox:
        assert msg.subject == "Walk update"
        assert len(msg.to) == 1


def test_send_test_email_command(outbox):
    call_command("send_test_email", "--to", "test@example.com")
    assert len(outbox) == 1
    assert outbox[0].to == ["test@example.com"]


def test_email_walk_registrants_command(outbox, registrations):
    call_command("email_walk_registrants", "--subject", "Hi", "--body", "Body text")
    assert len(outbox) == 2
