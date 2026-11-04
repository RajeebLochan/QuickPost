from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .. import selectors, services
from ..models import Conversation, Message
from ..ratelimit import rate_limit
from .common import service_action, verified_required

HISTORY_PAGE = 30


def _participant_conversation(request, pk):
    conversation = get_object_or_404(Conversation.objects.prefetch_related("participants__profile"), pk=pk)
    services.ensure_participant(conversation, request.user)
    return conversation


@login_required
def inbox(request):
    user = request.user
    query = request.GET.get("q", "").strip()[:60]
    last = Message.objects.filter(conversation=OuterRef("pk")).order_by("-created_at")
    others = selectors.active_users().exclude(pk=user.pk)
    conversations = (
        Conversation.objects.filter(participants=user, last_message_at__isnull=False)
        .annotate(
            unread=Count("messages", filter=Q(messages__is_read=False) & ~Q(messages__sender=user)),
            last_text=Subquery(last.values("content")[:1]),
            last_sender=Subquery(last.values("sender_id")[:1]),
        )
        .prefetch_related(Prefetch("participants", queryset=others, to_attr="others"))
        .order_by("-last_message_at")
    )
    if query:
        matching = (
            Conversation.participants.through.objects.filter(
                Q(user__username__icontains=query) | Q(user__profile__display_name__icontains=query)
            )
            .exclude(user=user)
            .values("conversation_id")
        )
        conversations = conversations.filter(pk__in=matching)
    page = selectors.paginate(request, conversations, 30)
    items = [c for c in page.items if c.others]
    for conversation in items:
        conversation.other = conversation.others[0]
    return render(
        request,
        "messages/inbox.html",
        {"conversations": items, "page": page, "query": query, "nav": "messages"},
    )


@login_required
def chat_room(request, pk):
    conversation = _participant_conversation(request, pk)
    other = conversation.get_other_participant(request.user)
    recent = list(conversation.messages.select_related("sender").order_by("-created_at")[: HISTORY_PAGE + 1])
    has_more = len(recent) > HISTORY_PAGE
    chat_messages = list(reversed(recent[:HISTORY_PAGE]))
    services.mark_conversation_read(conversation, request.user)
    blocked = other is not None and selectors.is_blocked_between(request.user, other)
    return render(
        request,
        "messages/chat.html",
        {
            "conversation": conversation,
            "other": other,
            "chat_messages": chat_messages,
            "has_more": has_more,
            "blocked": blocked,
            "nav": "messages",
        },
    )


@require_GET
@login_required
def history(request, pk):
    conversation = _participant_conversation(request, pk)
    qs = conversation.messages.select_related("sender").order_by("-created_at")
    before = request.GET.get("before")
    if before and before.isdigit():
        qs = qs.filter(pk__lt=int(before))
    rows = list(qs[: HISTORY_PAGE + 1])
    return JsonResponse(
        {
            "messages": [m.as_payload() for m in reversed(rows[:HISTORY_PAGE])],
            "has_more": len(rows) > HISTORY_PAGE,
        }
    )


@require_POST
@login_required
@verified_required
@rate_limit("message_send", limit=30, period=60)
@service_action
def send(request, pk):
    """HTTP path for sending; delivers through the same service and push as the socket."""
    conversation = _participant_conversation(request, pk)
    message = services.send_message(conversation, request.user, request.POST.get("content"))
    return JsonResponse({"message": message.as_payload()}, status=201)


@require_POST
@login_required
@service_action
def mark_read(request, pk):
    conversation = _participant_conversation(request, pk)
    return JsonResponse({"updated": services.mark_conversation_read(conversation, request.user)})
