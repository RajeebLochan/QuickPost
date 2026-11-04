"""Helpers shared by the view modules."""

import functools

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme

from .. import selectors
from ..models import Post
from ..services import ServiceError


def is_fetch(request):
    return request.headers.get("x-requested-with") == "fetch"


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next") or request.headers.get("referer")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def error_text(exc):
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc) or "Something went wrong."


def respond(request, data=None, *, fallback="feed", message=None, status=200):
    """JSON for fetch() calls, a redirect back (with an optional flash) for plain forms."""
    if is_fetch(request):
        payload = dict(data or {})
        if message:
            payload.setdefault("message", message)
        return JsonResponse(payload, status=status)
    if message:
        (messages.success if status < 400 else messages.error)(request, message)
    return redirect(safe_next(request, resolve_url(fallback)))


def service_action(view):
    """Translate service-layer exceptions into 400/403 responses for actions."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except (ValidationError, ServiceError) as exc:
            return respond(request, {"error": error_text(exc)}, message=error_text(exc), status=400)
        except PermissionDenied as exc:
            if is_fetch(request):
                return JsonResponse({"error": error_text(exc) or "Not allowed."}, status=403)
            raise

    return wrapper


def verified_required(view):
    """Posting, commenting and messaging need a confirmed email address."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if (
            settings.QUICKPOST["REQUIRE_EMAIL_VERIFICATION"]
            and request.method == "POST"
            and not request.user.profile.email_verified
        ):
            text = "Confirm your email address first. Check your inbox or resend the link from Settings."
            if is_fetch(request):
                return JsonResponse({"error": text}, status=403)
            messages.error(request, text)
            return redirect(safe_next(request, resolve_url("settings_account")))
        return view(request, *args, **kwargs)

    return wrapper


def get_visible_post(request, pk, annotate=False):
    qs = selectors.visible_posts(request.user)
    if annotate:
        qs = selectors.annotate_posts(qs, request.user)
    try:
        return qs.get(pk=pk)
    except Post.DoesNotExist:
        raise Http404("Post not found") from None


def owned_post(request, pk):
    post = get_object_or_404(Post.objects.select_related("user"), pk=pk)
    if post.user_id != request.user.pk:
        raise PermissionDenied("You can only change your own posts.")
    return post


def render_list(request, template, context, items_template):
    """Full page normally; just the items (for "Load more") when ?partial=1."""
    if request.GET.get("partial"):
        html = render_to_string(items_template, context, request=request)
        page = context.get("page")
        return JsonResponse({"html": html, "has_next": bool(page and page.has_next)})
    return render(request, template, context)
