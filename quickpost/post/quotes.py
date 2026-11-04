"""Daily quote: stored in the database, read from cache, never fetched during a request.

`python manage.py refresh_quote` asks Gemini for a new line (when
GEMINI_API_KEY is set) and stores it. Pages only read the newest stored
quote; if there is none, or it is older than two days, they show one of the
built-in lines below, which rotate by date so nothing stays frozen.
"""

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import DailyQuote

logger = logging.getLogger(__name__)

CACHE_KEY = "daily_quote:v2"
CACHE_SECONDS = 15 * 60
MAX_AGE = timedelta(hours=48)

PROMPT = (
    "Write exactly one short, impactful one-line quote with a life lesson inspired by the "
    "Ramayana and Mahabharata. Keep it clear, simple and timeless. End with a hyphen followed "
    "by the name of the character it is attributed to (for example Bhishma, Hanuman, Arjuna, "
    "Karna, Draupadi, Rama, Krishna, Sita or Vidura). Vary the theme: dharma, truth, courage, "
    "devotion, humility, ego or patience. Reply with the quote only."
)

FALLBACK_QUOTES = [
    ("True courage is facing danger when you are afraid.", "Krishna"),
    ("Do your duty and let go of the fruit of your actions.", "Krishna"),
    ("A promise kept in hardship is worth more than a kingdom won with ease.", "Rama"),
    ("Strength serves best when it bows to devotion.", "Hanuman"),
    ("Silence in the face of wrong is a wrong of its own.", "Vidura"),
    ("Patience is the bow that lets the arrow of truth fly straight.", "Arjuna"),
    ("Pride builds a fortress that falls on its builder.", "Bhishma"),
    ("Dignity cannot be taken; it can only be surrendered.", "Draupadi"),
    ("Give freely, for what is given is never lost.", "Karna"),
    ("The forest is no exile for a heart that walks with dharma.", "Sita"),
]

QUOTE_RE = re.compile(r"^[\"'“”]?(?P<text>.+?)[\"'“”]?\s+[-–—]\s*(?P<author>[\w .']{2,60})$")


class QuoteUnavailable(Exception):
    pass


def fallback_quote(today=None):
    today = today or timezone.localdate()
    text, author = FALLBACK_QUOTES[today.toordinal() % len(FALLBACK_QUOTES)]
    return {"text": text, "author": author, "source": "fallback"}


def current_quote():
    cached = cache.get(CACHE_KEY)
    if cached:
        return cached
    latest = DailyQuote.objects.first()
    if latest and timezone.now() - latest.created_at < MAX_AGE:
        data = {"text": latest.text, "author": latest.author, "source": latest.source}
    else:
        data = fallback_quote()
    cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return data


def parse_quote(raw):
    line = " ".join((raw or "").split())
    match = QUOTE_RE.match(line)
    if not match:
        raise QuoteUnavailable(f"Unexpected quote format: {line[:120]!r}")
    text = match.group("text").strip().strip("\"'“”")
    author = match.group("author").strip()
    if not 10 <= len(text) <= 300:
        raise QuoteUnavailable("Quote length out of range")
    return text, author


def api_key():
    key = settings.GEMINI_API_KEY
    if not key or key.lower().startswith("your"):
        return ""
    return key


def request_from_gemini():  # pragma: no cover - network call, mocked in tests
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key(), http_options=types.HttpOptions(timeout=20_000))
    response = client.models.generate_content(model=settings.GEMINI_MODEL, contents=PROMPT)
    return response.text or ""


def refresh_quote(fetch=None):
    """Fetch and store a new quote. Raises QuoteUnavailable on any failure."""
    if fetch is None:
        if not api_key():
            raise QuoteUnavailable("GEMINI_API_KEY is not set")
        fetch = request_from_gemini
    try:
        raw = fetch()
    except QuoteUnavailable:
        raise
    except Exception as exc:  # network and SDK errors vary; record and surface one type
        raise QuoteUnavailable(f"Gemini request failed: {exc.__class__.__name__}") from exc
    text, author = parse_quote(raw)
    quote = DailyQuote.objects.create(text=text, author=author, source=DailyQuote.Source.GEMINI)
    cache.delete(CACHE_KEY)
    logger.info("event=quote_refreshed quote=%s", quote.pk)
    return quote
