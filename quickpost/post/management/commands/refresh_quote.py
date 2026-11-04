from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from post.models import DailyQuote
from post.quotes import QuoteUnavailable, refresh_quote


class Command(BaseCommand):
    help = "Fetch a new daily quote from Gemini and store it. Safe to run from cron."

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-older-than",
            type=float,
            default=0,
            metavar="HOURS",
            help="Skip when the newest stored quote is younger than this many hours.",
        )

    def handle(self, *args, **options):
        hours = options["if_older_than"]
        latest = DailyQuote.objects.first()
        if hours and latest and timezone.now() - latest.created_at < timedelta(hours=hours):
            self.stdout.write("Quote is fresh; nothing to do.")
            return
        try:
            quote = refresh_quote()
        except QuoteUnavailable as exc:
            raise CommandError(
                f"Quote not refreshed: {exc}. The site keeps showing the last quote or a built-in one."
            ) from exc
        self.stdout.write(self.style.SUCCESS(f"Stored quote #{quote.pk}: {quote.text} - {quote.author}"))
