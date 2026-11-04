from django.urls import reverse

from post import selectors, services
from post.models import Block, FollowRequest, Notification, Post

from .base import FETCH, QuickPostTestCase, make_user


class FollowTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_user("alice")
        self.b = make_user("bob")
        self.login(self.a)

    def follow(self, username):
        return self.client.post(reverse("toggle_follow", args=[username]), **FETCH)

    def test_follow_and_unfollow(self):
        data = self.follow("bob").json()
        self.assertEqual((data["state"], data["followers_count"]), ("following", 1))
        self.assertTrue(selectors.is_following(self.a, self.b))
        self.assertTrue(Notification.objects.filter(recipient=self.b, verb="follow").exists())
        data = self.follow("bob").json()
        self.assertEqual((data["state"], data["followers_count"]), ("none", 0))
        self.assertFalse(Notification.objects.filter(recipient=self.b, verb="follow").exists())

    def test_cannot_follow_self(self):
        self.assertEqual(self.follow("alice").status_code, 400)

    def test_private_account_requires_approval(self):
        private = make_user("priv", private=True)
        self.assertEqual(self.follow("priv").json()["state"], "requested")
        self.assertFalse(selectors.is_following(self.a, private))
        request_obj = FollowRequest.objects.get()
        self.client.force_login(self.b)
        self.assertEqual(
            self.client.post(
                reverse("respond_follow_request", args=[request_obj.pk, "accept"]), **FETCH
            ).status_code,
            404,
        )
        self.client.force_login(private)
        response = self.client.post(
            reverse("respond_follow_request", args=[request_obj.pk, "accept"]), **FETCH
        )
        self.assertTrue(response.json()["accepted"])
        self.assertTrue(selectors.is_following(self.a, private))
        self.assertTrue(Notification.objects.filter(recipient=self.a, verb="follow_accept").exists())

    def test_cancel_request(self):
        make_user("priv", private=True)
        self.follow("priv")
        self.assertEqual(self.follow("priv").json()["state"], "none")
        self.assertFalse(FollowRequest.objects.exists())

    def test_follow_lists_paginate(self):
        for i in range(25):
            services.toggle_follow(make_user(f"fan{i:02d}"), self.b)
        response = self.client.get(reverse("followers", args=["bob"]))
        self.assertEqual(len(response.context["users"]), 20)
        self.assertTrue(response.context["page"].has_next)
        data = self.client.get(reverse("followers", args=["bob"]) + "?page=2&partial=1").json()
        self.assertIn("fan24", data["html"])
        self.assertFalse(data["has_next"])


class PrivacyTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner", private=True)
        self.follower = make_user("follower")
        self.stranger = make_user("stranger")
        services.toggle_follow(self.follower, self.owner)
        services.respond_to_follow_request(FollowRequest.objects.get(), self.owner, accept=True)
        self.post = self.post_as(self.owner, "secret plans #hidden")

    def test_stranger_sees_header_but_not_posts(self):
        self.login(self.stranger)
        response = self.client.get(reverse("profile", args=["owner"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This account is private")
        self.assertNotContains(response, "secret plans")
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse("followers", args=["owner"])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("explore")), "secret plans")
        self.assertNotContains(self.client.get(reverse("search") + "?q=secret&type=posts"), "secret plans")
        self.assertEqual(self.client.get(reverse("hashtag", args=["hidden"])).context["posts"], [])
        # Interacting with a hidden post is a 404, not a leak.
        self.assertEqual(
            self.client.post(reverse("post_react", args=[self.post.pk, "like"]), **FETCH).status_code, 404
        )

    def test_anonymous_cannot_see_private_posts(self):
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("profile", args=["owner"])), "secret plans")

    def test_follower_sees_posts(self):
        self.login(self.follower)
        self.assertContains(self.client.get(reverse("profile", args=["owner"])), "secret plans")
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get(reverse("feed")), "secret plans")

    def test_repost_of_private_post_not_shown_to_strangers(self):
        # Even if a repost existed (e.g. account made private later), strangers can't see the original.
        Post.objects.create(user=self.follower, repost_of=self.post, content="")
        self.login(self.stranger)
        response = self.client.get(reverse("profile", args=["follower"]))
        self.assertNotContains(response, "secret plans")


class BlockTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_user("alice")
        self.b = make_user("bob")
        services.toggle_follow(self.a, self.b)
        services.toggle_follow(self.b, self.a)
        self.b_post = self.post_as(self.b, "bob's post")
        self.login(self.a)

    def test_block_removes_follows_and_hides_both_ways(self):
        response = self.client.post(reverse("toggle_block", args=["bob"]), **FETCH)
        self.assertTrue(response.json()["blocked"])
        self.assertFalse(selectors.is_following(self.a, self.b))
        self.assertFalse(selectors.is_following(self.b, self.a))
        self.assertEqual(self.client.get(reverse("profile", args=["bob"])).status_code, 404)
        self.assertEqual(self.client.get(self.b_post.get_absolute_url()).status_code, 404)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(reverse("profile", args=["alice"])).status_code, 404)
        self.assertEqual(self.client.post(reverse("toggle_follow", args=["alice"]), **FETCH).status_code, 403)
        a_post = self.post_as(self.a, "alice's post")
        self.assertEqual(
            self.client.post(
                reverse("comment_create", args=[a_post.pk]), {"content": "hi"}, **FETCH
            ).status_code,
            404,
        )

    def test_unblock(self):
        services.block_user(self.a, self.b)
        response = self.client.post(reverse("toggle_block", args=["bob"]), **FETCH)
        self.assertFalse(response.json()["blocked"])
        self.assertFalse(Block.objects.exists())

    def test_blocked_users_cannot_message(self):
        conversation, _ = services.start_conversation(self.a, self.b)
        services.block_user(self.b, self.a)
        response = self.client.post(reverse("chat_send", args=[conversation.pk]), {"content": "hey"}, **FETCH)
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("message_user", args=["bob"]))
        self.assertEqual(response.status_code, 302)  # back to profile with an error, no conversation created


class ReportTests(QuickPostTestCase):
    def test_report_post_and_user(self):
        reporter = make_user("reporter")
        target = make_user("target")
        post = self.post_as(target, "spam spam")
        self.login(reporter)
        r1 = self.client.post(
            reverse("report"), {"reason": "spam", "target_type": "post", "target_id": post.pk}, **FETCH
        )
        r2 = self.client.post(
            reverse("report"),
            {"reason": "impersonation", "target_type": "user", "target_id": target.pk, "details": "fake"},
            **FETCH,
        )
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        self.assertEqual(target.reports_received.count(), 2)
        bad = self.client.post(
            reverse("report"), {"reason": "nope", "target_type": "post", "target_id": post.pk}, **FETCH
        )
        self.assertEqual(bad.status_code, 400)
        own = self.client.post(
            reverse("report"), {"reason": "spam", "target_type": "user", "target_id": reporter.pk}, **FETCH
        )
        self.assertEqual(own.status_code, 400)

    def test_admin_can_action_reports(self):
        from django.contrib.auth.models import User

        admin = User.objects.create_superuser("mod", "mod@example.com", "pass-12345!")
        target = make_user("target")
        post = self.post_as(target, "bad")
        report = services.create_report(make_user("r"), "spam", post=post)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:post_report_changelist")).status_code, 200)
        self.client.post(
            reverse("admin:post_report_changelist"),
            {"action": "remove_content", "_selected_action": [report.pk]},
        )
        report.refresh_from_db()
        self.assertEqual(report.status, "actioned")
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())
