import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import TransactionTestCase
from django.urls import path, reverse

from post import services
from post.consumers import LiveConsumer
from post.models import Conversation, Message, Notification

from .base import FETCH, QuickPostTestCase, make_user

application = URLRouter([path("ws/live/", LiveConsumer.as_asgi())])


class ConversationHttpTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_user("alice")
        self.b = make_user("bob")
        self.c = make_user("carol")

    def test_get_does_not_create_conversation(self):
        self.login(self.a)
        self.assertEqual(self.client.get(reverse("message_user", args=["bob"])).status_code, 405)
        self.assertFalse(Conversation.objects.exists())

    def test_post_creates_once_and_reuses(self):
        self.login(self.a)
        first = self.client.post(reverse("message_user", args=["bob"]))
        second = self.client.post(reverse("message_user", args=["bob"]))
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(first["Location"], second["Location"])
        self.client.post(reverse("message_user", args=["alice"]))  # self: refused
        self.assertEqual(Conversation.objects.count(), 1)

    def test_non_participants_are_refused(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        services.send_message(conversation, self.a, "private")
        self.login(self.c)
        self.assertEqual(self.client.get(reverse("chat_room", args=[conversation.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("chat_history", args=[conversation.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("chat_send", args=[conversation.pk]), {"content": "hi"}, **FETCH
            ).status_code,
            403,
        )
        self.assertEqual(Message.objects.count(), 1)

    def test_http_send_validates_and_pushes(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        self.login(self.a)
        self.assertEqual(
            self.client.post(
                reverse("chat_send", args=[conversation.pk]), {"content": "  "}, **FETCH
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                reverse("chat_send", args=[conversation.pk]), {"content": "x" * 1001}, **FETCH
            ).status_code,
            400,
        )
        with self.captureOnCommitCallbacks() as callbacks:
            response = self.client.post(
                reverse("chat_send", args=[conversation.pk]), {"content": "  hello  "}, **FETCH
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["message"]["content"], "hello")
        self.assertTrue(callbacks, "a realtime push is scheduled after commit")

    def test_chat_page_uses_chat_messages_and_marks_read(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        services.send_message(conversation, self.b, "UNIQUE-CHAT-TEXT")
        self.login(self.a)
        response = self.client.get(reverse("chat_room", args=[conversation.pk]))
        self.assertEqual(response.status_code, 200)
        # `messages` stays Django's flash storage; chat history has its own name.
        self.assertNotIsInstance(response.context["messages"], list)
        self.assertEqual(len(response.context["chat_messages"]), 1)
        # Chat text is never rendered as a flash banner.
        self.assertNotContains(response, 'id="flash-data"')
        self.assertTrue(Message.objects.get().is_read)
        self.assertFalse(Notification.objects.filter(recipient=self.a, is_read=False).exists())

    def test_flash_message_from_other_action_still_shows(self):
        self.login(self.a)
        self.client.post(reverse("settings_privacy"), {"is_private": "on"})
        response = self.client.get(reverse("settings_privacy"))
        self.assertContains(response, "Privacy settings saved")

    def test_history_pagination(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        for i in range(35):
            services.send_message(conversation, self.a if i % 2 else self.b, f"m{i}")
        self.login(self.a)
        page = self.client.get(reverse("chat_history", args=[conversation.pk])).json()
        self.assertEqual(len(page["messages"]), 30)
        self.assertTrue(page["has_more"])
        first_id = page["messages"][0]["id"]
        older = self.client.get(
            reverse("chat_history", args=[conversation.pk]) + f"?before={first_id}"
        ).json()
        self.assertEqual([m["content"] for m in older["messages"]], ["m0", "m1", "m2", "m3", "m4"])
        self.assertFalse(older["has_more"])

    def test_inbox_unread_counts_and_search(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        services.send_message(conversation, self.b, "one")
        services.send_message(conversation, self.b, "two")
        services.start_conversation(self.a, self.c)  # no messages yet: hidden from inbox
        self.login(self.a)
        response = self.client.get(reverse("inbox"))
        items = response.context["conversations"]
        self.assertEqual([(c.other.username, c.unread, c.last_text) for c in items], [("bob", 2, "two")])
        self.assertEqual(
            self.client.get(reverse("inbox") + "?q=bo").context["conversations"][0].other, self.b
        )
        self.assertEqual(self.client.get(reverse("inbox") + "?q=alice").context["conversations"], [])

    def test_message_notifications_are_deduplicated(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        for text in ("a", "b", "c"):
            services.send_message(conversation, self.a, text)
        self.assertEqual(Notification.objects.filter(recipient=self.b, verb="message").count(), 1)


class LiveSocketTests(TransactionTestCase):
    """WebSocket behaviour through the real consumer and channel layer."""

    def setUp(self):
        cache.clear()
        self.a = make_user("alice")
        self.b = make_user("bob")
        self.c = make_user("carol")
        self.conversation, _ = services.start_conversation(self.a, self.b)

    async def connect(self, user):
        communicator = WebsocketCommunicator(application, "/ws/live/")
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        assert connected
        return communicator

    async def receive_type(self, communicator, wanted, timeout=2):
        while True:
            event = json.loads(await communicator.receive_from(timeout=timeout))
            if event["type"] == wanted:
                return event

    def test_anonymous_connection_is_refused(self):
        async def run():
            communicator = WebsocketCommunicator(application, "/ws/live/")
            communicator.scope["user"] = AnonymousUser()
            connected, code = await communicator.connect()
            return connected, code

        connected, code = async_to_sync(run)()
        self.assertFalse(connected)
        self.assertEqual(code, 4401)

    def test_message_is_saved_and_delivered_to_every_participant(self):
        async def run():
            alice = await self.connect(self.a)
            bob = await self.connect(self.b)
            carol = await self.connect(self.c)
            await alice.send_to(
                text_data=json.dumps(
                    {
                        "action": "send",
                        "conversation": self.conversation.pk,
                        "content": "  hi bob  ",
                        "client_id": "c1",
                    }
                )
            )
            ack = await self.receive_type(alice, "ack")
            to_bob = await self.receive_type(bob, "message")
            to_alice = await self.receive_type(alice, "message")
            nothing_for_carol = await carol.receive_nothing(timeout=0.3)
            for c in (alice, bob, carol):
                await c.disconnect()
            return ack, to_bob, to_alice, nothing_for_carol

        ack, to_bob, to_alice, nothing_for_carol = async_to_sync(run)()
        message = Message.objects.get()
        self.assertEqual(message.content, "hi bob")
        self.assertEqual((ack["client_id"], ack["id"]), ("c1", message.pk))
        self.assertEqual(to_bob["message"]["content"], "hi bob")
        self.assertEqual(to_bob["message"]["id"], to_alice["message"]["id"])
        self.assertTrue(nothing_for_carol)

    def test_typing_goes_to_the_other_participant_only(self):
        async def run():
            alice = await self.connect(self.a)
            bob = await self.connect(self.b)
            await alice.send_to(
                text_data=json.dumps(
                    {"action": "typing", "conversation": self.conversation.pk, "typing": True}
                )
            )
            event = await self.receive_type(bob, "typing")
            echo = await alice.receive_nothing(timeout=0.3)
            await alice.disconnect()
            await bob.disconnect()
            return event, echo

        event, echo = async_to_sync(run)()
        self.assertEqual(
            (event["user_id"], event["typing"], event["conversation"]),
            (self.a.pk, True, self.conversation.pk),
        )
        self.assertTrue(echo)

    def test_non_participant_cannot_send_or_type(self):
        async def run():
            carol = await self.connect(self.c)
            await carol.send_to(
                text_data=json.dumps(
                    {
                        "action": "send",
                        "conversation": self.conversation.pk,
                        "content": "intrude",
                        "client_id": "x",
                    }
                )
            )
            err1 = await self.receive_type(carol, "error")
            await carol.send_to(
                text_data=json.dumps(
                    {"action": "typing", "conversation": self.conversation.pk, "typing": True}
                )
            )
            err2 = await self.receive_type(carol, "error")
            await carol.send_to(text_data="not json")
            err3 = await self.receive_type(carol, "error")
            await carol.disconnect()
            return err1, err2, err3

        err1, err2, err3 = async_to_sync(run)()
        self.assertEqual(err1["client_id"], "x")
        self.assertIn("not part", err2["error"])
        self.assertIn("Malformed", err3["error"])
        self.assertFalse(Message.objects.exists())

    def test_invalid_message_returns_error(self):
        async def run():
            alice = await self.connect(self.a)
            await alice.send_to(
                text_data=json.dumps(
                    {
                        "action": "send",
                        "conversation": self.conversation.pk,
                        "content": "x" * 1001,
                        "client_id": "big",
                    }
                )
            )
            err = await self.receive_type(alice, "error")
            await alice.disconnect()
            return err

        self.assertIn("1000", async_to_sync(run)()["error"])

    def test_read_receipt_reaches_sender(self):
        services.send_message(self.conversation, self.a, "did you see this")

        async def run():
            alice = await self.connect(self.a)
            bob = await self.connect(self.b)
            await bob.send_to(text_data=json.dumps({"action": "read", "conversation": self.conversation.pk}))
            event = await self.receive_type(alice, "read")
            await alice.disconnect()
            await bob.disconnect()
            return event

        event = async_to_sync(run)()
        self.assertEqual(event["reader_id"], self.b.pk)
        self.assertTrue(Message.objects.get().is_read)

    def test_http_fallback_also_pushes_to_sockets(self):
        async def run():
            bob = await self.connect(self.b)
            from channels.db import database_sync_to_async

            await database_sync_to_async(services.send_message)(self.conversation, self.a, "via http")
            event = await self.receive_type(bob, "message")
            await bob.disconnect()
            return event

        self.assertEqual(async_to_sync(run)()["message"]["content"], "via http")

    def test_notifications_are_pushed(self):
        post = services.create_post(self.b, "like me")

        async def run():
            bob = await self.connect(self.b)
            from channels.db import database_sync_to_async

            await database_sync_to_async(services.set_reaction)(post, self.a, "like")
            event = await self.receive_type(bob, "notification")
            await bob.disconnect()
            return event

        event = async_to_sync(run)()
        self.assertIn("liked your post", event["text"])
        self.assertIsNotNone(get_channel_layer())
