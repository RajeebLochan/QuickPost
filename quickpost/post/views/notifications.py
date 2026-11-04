from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import selectors, services
from ..models import FollowRequest, Notification
from .common import render_list, respond

PAGE_SIZE = 30


def _notifications(user):
    return (
        Notification.objects.filter(recipient=user)
        .select_related("actor__profile", "post", "comment")
        .order_by("-created_at")
    )


@login_required
def notifications(request):
    page = selectors.paginate(request, _notifications(request.user), PAGE_SIZE)
    context = {
        "page": page,
        "notifications": page.items,
        "nav": "notifications",
        "pending_requests": FollowRequest.objects.filter(to_user=request.user).count(),
    }
    response = render_list(request, "notifications.html", context, "partials/notification_items.html")
    # Everything shown has now been seen; it still renders as unread this one time.
    services.mark_notifications_read(
        request.user, ids=[n.pk for n in page.items if n.verb != Notification.Verb.MESSAGE]
    )
    return response


@login_required
def notifications_dropdown(request):
    items = list(_notifications(request.user).exclude(verb=Notification.Verb.MESSAGE)[:8])
    return render(request, "partials/notification_dropdown.html", {"notifications": items})


@login_required
def open_notification(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(notification.target_url)


@require_POST
@login_required
def mark_all_read(request):
    count = services.mark_notifications_read(request.user)
    return respond(request, {"updated": count}, fallback="notifications", message="All caught up")
