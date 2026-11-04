from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .. import selectors
from ..quotes import current_quote
from .common import render_list

PAGE_SIZE = 20


def home(request):
    if request.user.is_authenticated:
        return redirect("feed")
    preview = selectors.hydrate(
        selectors.annotate_posts(
            selectors.visible_posts(request.user).filter(repost_of__isnull=True), request.user
        ).order_by("-created_at")[:2],
        request.user,
    )
    return render(request, "landing.html", {"quote": current_quote(), "preview_posts": preview})


def sidebar_context(user):
    return {
        "quote": current_quote(),
        "suggestions": selectors.suggested_users(user, limit=4),
        "trending": selectors.trending_hashtags(user, limit=6),
    }


@login_required
def feed(request):
    page = selectors.paginate(
        request,
        selectors.annotate_posts(selectors.following_feed(request.user), request.user),
        PAGE_SIZE,
    )
    page.items = selectors.hydrate(page.items, request.user)
    context = {"page": page, "posts": page.items, "nav": "feed"}
    if not request.GET.get("partial"):
        context.update(sidebar_context(request.user))
    return render_list(request, "feed.html", context, "partials/post_items.html")


@login_required
def explore(request):
    page = selectors.paginate(request, selectors.explore_posts(request.user), PAGE_SIZE)
    page.items = selectors.hydrate(page.items, request.user)
    context = {"page": page, "posts": page.items, "nav": "explore"}
    if not request.GET.get("partial"):
        context.update(sidebar_context(request.user))
        context["people"] = selectors.suggested_users(request.user, limit=6)
    return render_list(request, "explore.html", context, "partials/post_items.html")
