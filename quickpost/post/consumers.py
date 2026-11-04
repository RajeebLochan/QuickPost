"""One WebSocket per browser tab, at /ws/live/.

Server -> client events: message, read, typing, notification.
Client -> server actions:
  {"action": "send", "conversation": id, "content": "..."}
  {"action": "typing", "conversation": id, "typing": true|false}
  {"action": "read", "conversation": id}
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError

from . import ratelimit, services
from .models import Conversation
from .realtime import user_group

logger = logging.getLogger(__name__)

PRESENCE_TTL = 60 * 60


def presence_key(user_id):
    return f"presence:{user_id}"


def is_online(user_id):
    return (cache.get(presence_key(user_id)) or 0) > 0


class LiveConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4401)
            return
        self.group = user_group(self.user.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await database_sync_to_async(self._presence)(1)

    async def disconnect(self, code):
        if getattr(self, "group", None):
            await self.channel_layer.group_discard(self.group, self.channel_name)
            await database_sync_to_async(self._presence)(-1)

    def _presence(self, delta):
        key = presence_key(self.user.pk)
        cache.add(key, 0, PRESENCE_TTL)
        try:
            value = cache.incr(key, delta)
        except ValueError:
            value = max(delta, 0)
            cache.set(key, value, PRESENCE_TTL)
        if value < 0:
            cache.set(key, 0, PRESENCE_TTL)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "")
            action = data["action"]
            conversation_id = int(data["conversation"])
        except (ValueError, KeyError, TypeError):
            await self._error("Malformed event.")
            return

        handler = {"send": self._send, "typing": self._typing, "read": self._read}.get(action)
        if handler is None:
            await self._error(f"Unknown action: {action}")
            return
        try:
            await handler(conversation_id, data)
        except (ValidationError, services.ServiceError) as exc:
            await self._error(" ".join(getattr(exc, "messages", [str(exc)])), data.get("client_id"))
        except (PermissionDenied, Conversation.DoesNotExist):
            await self._error("You're not part of this conversation.", data.get("client_id"))
        except ratelimit.RateLimited:
            await self._error("You're sending messages too quickly.", data.get("client_id"))

    async def _send(self, conversation_id, data):
        message = await database_sync_to_async(self._save_message)(conversation_id, data.get("content"))
        # Delivery to every participant (including this tab) happens through
        # the user groups once the transaction commits; just acknowledge here.
        await self.send(
            text_data=json.dumps({"type": "ack", "client_id": data.get("client_id"), "id": message.pk})
        )

    def _save_message(self, conversation_id, content):
        ratelimit.check("message_send", f"u{self.user.pk}", 30, 60)
        if not self.user.profile.email_verified and settings.QUICKPOST["REQUIRE_EMAIL_VERIFICATION"]:
            raise PermissionDenied
        conversation = Conversation.objects.get(pk=conversation_id)
        return services.send_message(conversation, self.user, content if isinstance(content, str) else "")

    async def _typing(self, conversation_id, data):
        others = await database_sync_to_async(self._other_participants)(conversation_id)
        event = {
            "type": "typing",
            "conversation": conversation_id,
            "user_id": self.user.pk,
            "typing": bool(data.get("typing")),
        }
        for other_id in others:
            await self.channel_layer.group_send(user_group(other_id), {"type": "live.event", "event": event})

    def _other_participants(self, conversation_id):
        conversation = Conversation.objects.get(pk=conversation_id)
        services.ensure_participant(conversation, self.user)
        return list(conversation.participants.exclude(pk=self.user.pk).values_list("pk", flat=True))

    async def _read(self, conversation_id, data):
        await database_sync_to_async(self._mark_read)(conversation_id)

    def _mark_read(self, conversation_id):
        conversation = Conversation.objects.get(pk=conversation_id)
        services.mark_conversation_read(conversation, self.user)

    async def live_event(self, event):
        await self.send(text_data=json.dumps(event["event"]))

    async def _error(self, message, client_id=None):
        await self.send(text_data=json.dumps({"type": "error", "error": message, "client_id": client_id}))
