"""Send a single test email to verify outbound delivery end to end."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from libraries.emails import send_email


class Command(BaseCommand):
    help = "Send a single test email to confirm outbound delivery and the From address."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Recipient email address.")

    def handle(self, *args, **options):
        to = options["to"]
        self.stdout.write("Backend: {}".format(settings.EMAIL_BACKEND))
        self.stdout.write("From: {}".format(settings.DEFAULT_FROM_EMAIL))

        sent = send_email(
            subject="Bookworm test email",
            to=to,
            text_body=(
                "This is a test email from Bookworm.\n\n"
                "If you are reading this, outbound email is working and the "
                "From address is correct.\n"
            ),
            html_body=(
                "<p>This is a test email from Bookworm.</p>"
                "<p>If you are reading this, outbound email is working and the "
                "From address is correct.</p>"
            ),
        )

        if sent:
            self.stdout.write(self.style.SUCCESS("Sent test email to {}.".format(to)))
        else:
            raise CommandError("Email backend reported 0 messages sent.")
