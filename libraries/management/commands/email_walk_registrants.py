"""Broadcast a subject + message to every Library Walk registrant."""

from django.core.management.base import BaseCommand, CommandError

from libraries.models import LibraryWalkRegistration
from libraries.emails import send_walk_broadcast


class Command(BaseCommand):
    help = "Email all Library Walk registrants a subject and message."

    def add_arguments(self, parser):
        parser.add_argument("--subject", required=True, help="Email subject line.")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--body", help="Message body as a string.")
        group.add_argument(
            "--body-file",
            help="Path to a UTF-8 text file containing the message body.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count recipients and render messages without sending.",
        )

    def handle(self, *args, **options):
        subject = options["subject"]

        if options.get("body_file"):
            try:
                with open(options["body_file"], "r", encoding="utf-8") as handle:
                    body = handle.read().strip()
            except OSError as exc:
                raise CommandError("Could not read body file: {}".format(exc))
        else:
            body = (options.get("body") or "").strip()

        if not body:
            raise CommandError("Message body is empty.")

        registrations = LibraryWalkRegistration.objects.all()
        if not registrations.exists():
            self.stdout.write("No registrants found.")
            return

        sent = send_walk_broadcast(
            registrations, subject, body, dry_run=options["dry_run"]
        )

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("Dry run: would email {} registrant(s).".format(sent))
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Emailed {} registrant(s).".format(sent))
            )
