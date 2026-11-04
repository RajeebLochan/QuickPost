from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .. import selectors, services
from ..forms import ReportForm
from ..models import Comment, FollowRequest, Post
from ..ratelimit import rate_limit
from .common import render_list, respond, service_action
from .pages import PAGE_SIZE


def _profile_user(request, username):
    user = get_object_or_404(User.objects.select_related("profile"), username=username)
    if not selectors.can_view_profile(request.user, user):
        raise Http404("Profile not available")
    return user


def _follow_state(viewer, user):
    if selectors.is_following(viewer, user):
        return "following"
    if selectors.has_pending_request(viewer, user):
        return "requested"
    return "none"


def profile(request, username):
    user = _profile_user(request, username)
    tab = "media" if request.GET.get("tab") == "media" else "posts"
    can_view = selectors.can_view_posts(request.user, user)
    context = {
        "profile_user": user,
        "profile": user.profile,
        "stats": selectors.profile_stats(user),
        "is_own": request.user.is_authenticated and request.user.pk == user.pk,
        "can_view": can_view,
        "follow_state": _follow_state(request.user, user),
        "follows_you": selectors.is_following(user, request.user) if request.user.is_authenticated else False,
        "blocked": selectors.has_blocked(request.user, user),
        "tab": tab,
        "nav": "profile" if request.user.is_authenticated and request.user.pk == user.pk else "",
        "report_reasons": ReportForm.base_fields["reason"].choices,
    }
    if can_view:
        posts = selectors.visible_posts(request.user).filter(user=user)
        if tab == "media":
            posts = posts.filter(images__isnull=False, repost_of__isnull=True).distinct()
        page = selectors.paginate(
            request, selectors.annotate_posts(posts, request.user).order_by("-created_at"), PAGE_SIZE
        )
        page.items = selectors.hydrate(page.items, request.user)
        context.update(page=page, posts=page.items)
    return render_list(request, "profiles/profile.html", context, "partials/post_items.html")


def _follow_list(request, username, which):
    user = _profile_user(request, username)
    if not selectors.can_view_posts(request.user, user):
        raise PermissionDenied("This account is private.")
    ids = selectors.follower_user_ids(user) if which == "followers" else selectors.following_user_ids(user)
    users = selectors.with_follow_state(
        selectors.active_users(request.user)
        .filter(pk__in=ids)
        .annotate(follower_total=Count("profile__followers", distinct=True))
        .order_by("username"),
        request.user,
    )
    page = selectors.paginate(request, users, PAGE_SIZE)
    context = {
        "profile_user": user,
        "which": which,
        "page": page,
        "users": page.items,
        "stats": selectors.profile_stats(user),
    }
    return render_list(request, "profiles/follow_list.html", context, "partials/user_items.html")


@login_required
def followers(request, username):
    return _follow_list(request, username, "followers")


@login_required
def following(request, username):
    return _follow_list(request, username, "following")


@require_POST
@login_required
@rate_limit("follow", limit=30, period=60)
@service_action
def toggle_follow(request, username):
    target = get_object_or_404(User, username=username)
    result = services.toggle_follow(request.user, target)
    text = {"following": "Following", "requested": "Request sent", "none": "Unfollowed"}[result["state"]]
    return respond(request, result, fallback=target.profile.get_absolute_url(), message=text)


@login_required
def follow_requests(request):
    pending = FollowRequest.objects.filter(to_user=request.user).select_related("from_user__profile")
    page = selectors.paginate(request, pending, PAGE_SIZE)
    return render_list(
        request,
        "profiles/follow_requests.html",
        {"page": page, "requests": page.items, "nav": "notifications"},
        "partials/follow_request_items.html",
    )


@require_POST
@login_required
@service_action
def respond_follow_request(request, pk, decision):
    request_obj = get_object_or_404(FollowRequest, pk=pk, to_user=request.user)
    accepted = services.respond_to_follow_request(request_obj, request.user, decision == "accept")
    return respond(
        request,
        {"accepted": accepted},
        fallback="follow_requests",
        message="Request accepted" if accepted else "Request declined",
    )


@require_POST
@login_required
@service_action
def toggle_block(request, username):
    target = get_object_or_404(User, username=username)
    if selectors.has_blocked(request.user, target):
        services.unblock_user(request.user, target)
        return respond(
            request, {"blocked": False}, fallback="settings_privacy", message=f"Unblocked @{target.username}"
        )
    services.block_user(request.user, target)
    return respond(request, {"blocked": True}, fallback="feed", message=f"Blocked @{target.username}")


@require_POST
@login_required
@rate_limit("report", limit=10, period=3600)
@service_action
def report(request):
    form = ReportForm(request.POST)
    if not form.is_valid():
        return respond(request, {"error": "Choose a reason."}, message="Choose a reason.", status=400)
    data = form.cleaned_data
    target = {"post": None, "comment": None, "user": None}
    if data["target_type"] == "post":
        target["post"] = get_object_or_404(Post, pk=data["target_id"])
    elif data["target_type"] == "comment":
        target["comment"] = get_object_or_404(Comment, pk=data["target_id"])
    else:
        target["user"] = get_object_or_404(User, pk=data["target_id"])
    services.create_report(request.user, data["reason"], data["details"], **target)
    return respond(request, {"reported": True}, message="Thanks. A moderator will review this report.")


@require_POST
@login_required
def message_user(request, username):
    target = get_object_or_404(User, username=username)
    try:
        conversation, _ = services.start_conversation(request.user, target)
    except (services.ServiceError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect(target.profile.get_absolute_url())
    return redirect("chat_room", pk=conversation.pk)
