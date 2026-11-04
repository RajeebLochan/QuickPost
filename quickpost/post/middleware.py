from datetime import timedelta

from django.contrib.auth import logout
from django.core.cache import cache
from django.utils import timezone

from .models import UserProfile

LAST_SEEN_INTERVAL = timedelta(minutes=2)


class ActiveAccountMiddleware:
    """Makes sure signed-in users have a profile, logs out deactivated
    accounts, and records `last_seen` at most every two minutes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.is_deactivated:
                logout(request)
            else:
                key = f"last_seen:{user.pk}"
                if cache.add(key, 1, int(LAST_SEEN_INTERVAL.total_seconds())):
                    UserProfile.objects.filter(pk=profile.pk).update(last_seen=timezone.now())
        return self.get_response(request)
