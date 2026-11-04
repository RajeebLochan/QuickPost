from django.conf import settings

from .models import Notification
from .quotes import current_quote
from .services import unread_message_count


def navigation(request):
    user = getattr(request, "user", None)
    data = {
        "POST_MAX_LENGTH": 240,
        "MAX_IMAGES_PER_POST": settings.QUICKPOST["MAX_IMAGES_PER_POST"],
        # Callable: only evaluated by templates that actually show the quote.
        "daily_quote": current_quote,
    }
    if user is None or not user.is_authenticated:
        return data
    data["unread_notifications"] = (
        Notification.objects.filter(recipient=user, is_read=False)
        .exclude(verb=Notification.Verb.MESSAGE)
        .count()
    )
    data["unread_messages"] = unread_message_count(user)
    return data
