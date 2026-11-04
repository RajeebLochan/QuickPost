"""Small fixed-window rate limiter backed by Django's cache.

Uses Redis in production (shared across workers) and the local-memory cache
in development.
"""

import functools
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


class RateLimited(Exception):
    def __init__(self, scope):
        super().__init__(scope)
        self.scope = scope


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def hit(scope, identity, limit, period):
    """Count one hit; return True while the caller is within `limit` per `period` seconds."""
    if not settings.QUICKPOST["RATE_LIMITS_ENABLED"]:
        return True
    key = f"rl:{scope}:{identity}"
    cache.add(key, 0, timeout=period)
    try:
        count = cache.incr(key)
    except ValueError:  # key expired between add and incr
        cache.set(key, 1, timeout=period)
        count = 1
    if count > limit:
        logger.warning("event=rate_limited scope=%s identity=%s", scope, identity)
        return False
    return True


def check(scope, identity, limit, period):
    if not hit(scope, identity, limit, period):
        raise RateLimited(scope)


def wants_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get(
        "accept", ""
    )


def too_many(request):
    message = "You're doing that too often. Try again in a minute."
    if wants_json(request):
        return JsonResponse({"error": message}, status=429)
    return render(request, "429.html", {"message": message}, status=429)


def rate_limit(scope, limit, period=60, methods=("POST",), by="user"):
    """View decorator. `by` is "user" (falls back to IP when anonymous) or "ip"."""

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method in methods:
                if by == "user" and request.user.is_authenticated:
                    identity = f"u{request.user.pk}"
                else:
                    identity = f"ip{client_ip(request)}"
                if not hit(scope, identity, limit, period):
                    return too_many(request)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
