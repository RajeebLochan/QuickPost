"""Push events to connected browsers through the channel layer.

Each logged-in browser tab holds one WebSocket (see consumers.LiveConsumer)
subscribed to the group `user.<id>`. Everything real-time (messages, typing,
read receipts, notifications) is delivered to user groups, so one socket per
tab is enough and authorization happens when the event is produced.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)


def user_group(user_id):
    return f"user.{user_id}"


def push(user_ids, event):
    layer = get_channel_layer()
    if layer is None:
        return
    for user_id in set(user_ids):
        try:
            async_to_sync(layer.group_send)(user_group(user_id), {"type": "live.event", "event": event})
        except Exception:  # The database write already succeeded; never fail the request on a push.
            logger.exception("event=realtime_push_failed user=%s type=%s", user_id, event.get("type"))


def push_on_commit(user_ids, event):
    """Send after the surrounding transaction commits, so clients never see rolled-back data."""
    user_ids = list(user_ids)
    transaction.on_commit(lambda: push(user_ids, event))
