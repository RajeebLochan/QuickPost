from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .. import selectors, services
from ..forms import EditPostForm, PostForm
from ..models import Comment, Post
from ..ratelimit import rate_limit
from ..services import ServiceError
from .common import (
    error_text,
    get_visible_post,
    is_fetch,
    owned_post,
    render_list,
    respond,
    service_action,
    verified_required,
)

COMMENTS_PAGE = 20


@login_required
@verified_required
@rate_limit("post_create", limit=10, period=60)
def compose(request):
    quote_of = None
    quote_id = request.POST.get("quote_of") or request.GET.get("quote")
    if quote_id:
        quote_of = get_visible_post(request, quote_id, annotate=True)
        quote_of = selectors.hydrate([quote_of], request.user)[0]

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if quote_of is not None:
            form.fields["content"].required = True
        if form.is_valid():
            try:
                post = services.create_post(
                    request.user,
                    form.cleaned_data["content"],
                    images=form.cleaned_data["images"],
                    repost_of=quote_of,
                )
            except (ValidationError, ServiceError) as exc:
                form.add_error(None, error_text(exc))
            else:
                if is_fetch(request):
                    return JsonResponse({"ok": True, "url": post.get_absolute_url()})
                messages.success(request, "Posted")
                return redirect("feed")
        if is_fetch(request):
            errors = [e for errs in form.errors.values() for e in errs]
            return JsonResponse({"error": " ".join(errors)}, status=400)
    else:
        form = PostForm()
    return render(request, "posts/compose.html", {"form": form, "quote_of": quote_of, "nav": "compose"})


def post_detail(request, pk):
    post = get_visible_post(request, pk, annotate=True)
    if post.is_plain_repost:
        return redirect("post_detail", pk=post.repost_of_id)
    post = selectors.hydrate([post], request.user)[0]
    comments_page = _comments_page(request, post)
    return render(
        request,
        "posts/detail.html",
        {"post": post, "comments_page": comments_page, "comments": comments_page.items},
    )


def _comments_page(request, post):
    hidden = []
    if request.user.is_authenticated:
        hidden = list(selectors.blocked_by_user_ids(request.user).values_list("blocked_id", flat=True))
        hidden += list(selectors.blockers_of_user_ids(request.user).values_list("blocker_id", flat=True))
    replies = (
        Comment.objects.exclude(user_id__in=hidden)
        .filter(user__profile__is_deactivated=False)
        .select_related("user__profile")
        .order_by("created_at")
    )
    top = (
        Comment.objects.filter(post=post, parent__isnull=True, user__profile__is_deactivated=False)
        .exclude(user_id__in=hidden)
        .select_related("user__profile")
        .prefetch_related(Prefetch("replies", queryset=replies, to_attr="visible_replies"))
        .order_by("created_at")
    )
    return selectors.paginate(request, top, COMMENTS_PAGE)


def comments_list(request, pk):
    post = get_visible_post(request, pk)
    page = _comments_page(request, post)
    return render_list(
        request,
        "posts/detail.html",
        {"post": post, "comments_page": page, "comments": page.items, "page": page},
        "partials/comment_items.html",
    )


@login_required
def post_edit(request, pk):
    post = owned_post(request, pk)
    if post.is_plain_repost:
        messages.error(request, "Reposts can't be edited.")
        return redirect("post_detail", pk=post.repost_of_id)
    form = EditPostForm(request.POST if request.method == "POST" else None, initial={"content": post.content})
    if request.method == "POST" and form.is_valid():
        try:
            services.edit_post(post, request.user, form.cleaned_data["content"])
        except (ValidationError, ServiceError) as exc:
            form.add_error("content", error_text(exc))
        else:
            messages.success(request, "Post updated")
            return redirect(post)
    return render(request, "posts/edit.html", {"form": form, "post": post})


@login_required
def post_delete(request, pk):
    post = get_object_or_404(Post.objects.select_related("user"), pk=pk)
    if request.method == "POST":
        services.delete_post(post, request.user)
        return respond(request, {"deleted": True}, fallback="feed", message="Post deleted")
    owned_post(request, pk)
    return render(request, "posts/delete.html", {"post": post})


@require_POST
@login_required
@service_action
def react(request, pk, kind):
    post = get_visible_post(request, pk)
    return respond(request, services.set_reaction(post, request.user, kind), fallback=post.get_absolute_url())


@require_POST
@login_required
@verified_required
@service_action
def repost(request, pk):
    post = get_visible_post(request, pk)
    result = services.toggle_repost(post, request.user)
    message = "Reposted" if result["reposted"] else "Repost removed"
    return respond(request, result, fallback=post.get_absolute_url(), message=message)


@require_POST
@login_required
@service_action
def bookmark(request, pk):
    post = get_visible_post(request, pk)
    result = services.toggle_bookmark(post, request.user)
    message = "Saved" if result["saved"] else "Removed from saved"
    return respond(request, result, fallback=post.get_absolute_url(), message=message)


@require_POST
@login_required
@verified_required
@rate_limit("comment_create", limit=20, period=60)
@service_action
def comment_create(request, pk):
    post = get_visible_post(request, pk)
    parent = None
    parent_id = request.POST.get("parent")
    if parent_id:
        parent = get_object_or_404(Comment, pk=parent_id, post=post)
    comment = services.add_comment(post, request.user, request.POST.get("content"), parent=parent)
    comment.visible_replies = []
    html = render_to_string("partials/comment.html", {"comment": comment, "post": post}, request=request)
    return respond(
        request,
        {
            "html": html,
            "id": comment.pk,
            "parent": comment.parent_id,
            "comments_count": post.comments.count(),
        },
        fallback=comment.get_absolute_url(),
        message="Comment added",
    )


@require_POST
@login_required
@service_action
def comment_delete(request, pk):
    comment = get_object_or_404(Comment.objects.select_related("post"), pk=pk)
    post = comment.post
    services.delete_comment(comment, request.user)
    return respond(
        request,
        {"deleted": True, "comments_count": post.comments.count()},
        fallback=post.get_absolute_url(),
        message="Comment deleted",
    )
