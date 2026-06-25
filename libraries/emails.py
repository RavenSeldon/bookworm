"""
Bookworm: outbound email helpers.

A single send path so every message goes out as DEFAULT_FROM_EMAIL with a
consistent Reply-To. The Library Walk broadcast reuses one SMTP connection and
sends one message per recipient (addresses are never shared). With no
RESEND_API_KEY set, settings route this through the console backend, so local
dev never sends real mail.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string


WALK_BROADCAST_FOOTER = (
    "You are receiving this because you registered for the Bookworm Free "
    "Little Library Walk. Reply to this email to be removed from future updates."
)


def _reply_to_list(reply_to=None):
    addr = reply_to or getattr(settings, "EMAIL_REPLY_TO", "")
    return [addr] if addr else None


def send_email(subject, to, text_body, html_body=None, *,
               reply_to=None, connection=None, fail_silently=False):
    """
    Send one email as DEFAULT_FROM_EMAIL with a text part and an optional HTML
    part. ``to`` may be a string or a list. Returns the number of messages sent.
    """
    recipients = [to] if isinstance(to, str) else list(to)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        reply_to=_reply_to_list(reply_to),
        connection=connection,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=fail_silently)


def send_walk_broadcast(registrations, subject, body, *, dry_run=False):
    """
    Email each Library Walk registrant individually over a single connection.
    Personalizes with the registrant's name and appends an identifying and
    opt-out footer. Returns the number of recipients processed (dry-run
    recipients are counted but nothing is sent).
    """
    connection = get_connection()
    sent = 0
    opened = False
    try:
        for registration in registrations:
            if not registration.email:
                continue
            greeting = "Hi {},".format(registration.name) if registration.name else "Hi,"
            text_body = "{}\n\n{}\n\n--\n{}".format(greeting, body, WALK_BROADCAST_FOOTER)
            html_body = render_to_string(
                "emails/walk_broadcast.html",
                {"greeting": greeting, "body": body, "footer": WALK_BROADCAST_FOOTER},
            )
            if not dry_run:
                if not opened:
                    connection.open()
                    opened = True
                send_email(
                    subject,
                    registration.email,
                    text_body,
                    html_body,
                    connection=connection,
                )
            sent += 1
    finally:
        if opened:
            connection.close()
    return sent
