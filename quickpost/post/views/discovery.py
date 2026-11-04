from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect

from .. import selectors
from ..models import Hashtag
from .common import render_list
from .pages import PAGE_SIZE, sidebar_context

SEARCH_TYPES = ("people", "posts", "tags")


@login_required
def search(request):
    query = request.GET.get("q", "").strip()[:100]
    kind = request.GET.get("type", "people")
    if kind not in SEARCH_TYPES:
        kind = "people"
    if query.startswith("#") and len(query) > 1 and kind != "posts":
        kind = "tags"

    context = {"query": query, "kind": kind, "nav": "search", "types": SEARCH_TYPES}
    page = None
    if query:
        if kind == "people":
            term = query.lstrip("@")
            users = selectors.with_follow_state(
                selectors.active_users(request.user)
                .filter(Q(username__icontains=term) | Q(profile__display_name__icontains=term))
                .annotate(follower_total=Count("profile__followers", distinct=True))
                .order_by("-follower_total", "username"),
                request.user,
            )
            page = selectors.paginate(request, users, PAGE_SIZE)
            context["users"] = page.items
            items_template = "partials/user_items.html"
        elif kind == "posts":
            posts = selectors.annotate_posts(
                selectors.visible_posts(request.user).filter(
                    repost_of__isnull=True, content__icontains=query
                ),
                request.user,
            ).order_by("-created_at")
            page = selectors.paginate(request, posts, PAGE_SIZE)
            page.items = selectors.hydrate(page.items, request.user)
            context["posts"] = page.items
            items_template = "partials/post_items.html"
        else:
            visible = selectors.visible_posts(request.user).values("pk")
            tags = (
                Hashtag.objects.filter(name__istartswith=query.lstrip("#").lower())
                .annotate(uses=Count("posts", filter=Q(posts__in=visible), distinct=True))
                .filter(uses__gt=0)
                .order_by("-uses", "name")
            )
            page = selectors.paginate(request, tags, PAGE_SIZE)
            context["tags"] = page.items
            items_template = "partials/tag_items.html"
        context["page"] = page
    else:
        items_template = "partials/user_items.html"
        context.update(sidebar_context(request.user))
        context["people"] = selectors.suggested_users(request.user, limit=8)
    return render_list(request, "search.html", context, items_template)


@login_required
def hashtag(request, name):
    tag = Hashtag.objects.filter(name=name.lower()).first()
    if tag is None:
        raise Http404("No posts with this hashtag")
    if tag.name != name:
        return redirect("hashtag", name=tag.name)
    posts = selectors.annotate_posts(
        selectors.visible_posts(request.user).filter(hashtags=tag), request.user
    ).order_by("-created_at")
    page = selectors.paginate(request, posts, PAGE_SIZE)
    page.items = selectors.hydrate(page.items, request.user)
    context = {"tag": tag, "page": page, "posts": page.items, "nav": "explore"}
    return render_list(request, "hashtag.html", context, "partials/post_items.html")


@login_required
def saved(request):
    posts = selectors.annotate_posts(
        selectors.visible_posts(request.user).filter(bookmarks__user=request.user), request.user
    ).order_by("-bookmarks__created_at")
    page = selectors.paginate(request, posts, PAGE_SIZE)
    page.items = selectors.hydrate(page.items, request.user)
    context = {"page": page, "posts": page.items, "nav": "saved"}
    return render_list(request, "saved.html", context, "partials/post_items.html")
