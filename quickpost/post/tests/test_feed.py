from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from post import quotes, selectors, services
from post.models import DailyQuote, Notification, Post

from .base import FETCH, QuickPostTestCase, image_file, make_user


class FeedTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.me = make_user("me")
        self.friend = make_user("friend")
        self.stranger = make_user("stranger")
        services.toggle_follow(self.me, self.friend)
        self.login(self.me)

    def test_following_feed_contains_followed_and_own_posts_only(self):
        self.post_as(self.friend, "from friend")
        self.post_as(self.me, "from me")
        self.post_as(self.stranger, "from stranger")
        response = self.client.get(reverse("feed"))
        self.assertContains(response, "from friend")
        self.assertContains(response, "from me")
        self.assertNotContains(response, "from stranger")

    def test_reposts_appear_with_original_content(self):
        original = self.post_as(self.stranger, "worth sharing")
        services.toggle_repost(original, self.friend)
        response = self.client.get(reverse("feed"))
        self.assertContains(response, "worth sharing")
        self.assertContains(response, "reposted")

    def test_feed_pagination_and_partial_load(self):
        for i in range(45):
            self.post_as(self.friend, f"post number {i}")
        page1 = self.client.get(reverse("feed"))
        self.assertEqual(len(page1.context["posts"]), 20)
        self.assertTrue(page1.context["page"].has_next)
        page3 = self.client.get(reverse("feed") + "?page=3&partial=1").json()
        self.assertFalse(page3["has_next"])
        self.assertIn("post number 0", page3["html"])
        self.assertEqual(self.client.get(reverse("feed") + "?page=abc").status_code, 200)

    def test_feed_query_count_is_constant(self):
        def count_for(n):
            Post.objects.all().delete()
            for i in range(n):
                post = self.post_as(
                    self.friend, f"#tag post {i}", images=[image_file()] if i % 3 == 0 else []
                )
                services.add_comment(post, self.stranger, "nice")
                services.set_reaction(post, self.stranger, "like")
                if i % 4 == 0:
                    services.toggle_repost(post, self.stranger)
                    services.toggle_repost(post, self.me)
            self.client.get(reverse("feed"))  # warm the per-user caches (last_seen, quote)
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse("feed"))
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        small, large = count_for(3), count_for(20)
        self.assertEqual(small, large, "feed queries must not grow with the number of posts")
        self.assertLessEqual(large, 25)

    def test_explore_ranks_by_engagement_and_hides_private(self):
        quiet = self.post_as(self.stranger, "quiet post")
        busy = self.post_as(self.stranger, "busy post")
        for i in range(3):
            services.set_reaction(busy, make_user(f"liker{i}"), "like")
        private = make_user("priv", private=True)
        self.post_as(private, "private post")
        old = self.post_as(self.stranger, "ancient post")
        Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
        posts = self.client.get(reverse("explore")).context["posts"]
        texts = [p.display.content for p in posts]
        self.assertEqual(texts[0], "busy post")
        self.assertIn(quiet.content, texts)
        self.assertNotIn("private post", texts)
        self.assertNotIn("ancient post", texts)

    def test_suggestions_exclude_followed_self_and_blocked(self):
        blocked = make_user("blocked")
        services.block_user(self.me, blocked)
        names = [u.username for u in selectors.suggested_users(self.me, limit=10)]
        self.assertIn("stranger", names)
        self.assertNotIn("friend", names)
        self.assertNotIn("me", names)
        self.assertNotIn("blocked", names)


class SearchTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.me = make_user("searcher")
        make_user("meera", display_name="Meera Iyer")
        self.login(self.me)

    def test_people_posts_tags(self):
        author = make_user("writer")
        self.post_as(author, "Rain in #Pune today")
        people = self.client.get(reverse("search") + "?q=iyer").context["users"]
        self.assertEqual([u.username for u in people], ["meera"])
        posts = self.client.get(reverse("search") + "?q=rain&type=posts").context["posts"]
        self.assertEqual(len(posts), 1)
        tags = self.client.get(reverse("search") + "?q=%23pu").context["tags"]
        self.assertEqual([t.name for t in tags], ["pune"])
        self.assertEqual(self.client.get(reverse("hashtag", args=["Pune"])).status_code, 302)
        self.assertEqual(len(self.client.get(reverse("hashtag", args=["pune"])).context["posts"]), 1)

    def test_empty_search_shows_suggestions(self):
        response = self.client.get(reverse("search"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("people", response.context)


class NotificationTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner")
        self.fan = make_user("fan")
        self.post = self.post_as(self.owner, "notify me")

    def test_activity_creates_notifications(self):
        services.set_reaction(self.post, self.fan, "like")
        services.add_comment(self.post, self.fan, "hi")
        services.toggle_follow(self.fan, self.owner)
        services.create_post(self.fan, "hey @owner")
        verbs = set(Notification.objects.filter(recipient=self.owner).values_list("verb", flat=True))
        self.assertEqual(verbs, {"like", "comment", "follow", "mention"})

    def test_unlike_withdraws_and_relike_does_not_duplicate(self):
        services.set_reaction(self.post, self.fan, "like")
        services.set_reaction(self.post, self.fan, "like")
        self.assertFalse(Notification.objects.filter(verb="like").exists())
        services.set_reaction(self.post, self.fan, "like")
        Notification.objects.update(is_read=True)
        services.set_reaction(self.post, self.fan, "like")
        services.set_reaction(self.post, self.fan, "like")
        self.assertEqual(Notification.objects.filter(verb="like").count(), 1)

    def test_no_self_notifications(self):
        services.set_reaction(self.post, self.owner, "like")
        services.add_comment(self.post, self.owner, "me")
        self.assertFalse(Notification.objects.exists())

    def test_page_dropdown_open_and_mark_all(self):
        services.set_reaction(self.post, self.fan, "like")
        services.add_comment(self.post, self.fan, "hello")
        self.login(self.owner)
        self.assertContains(self.client.get(reverse("feed")), 'data-badge="notifications">2<')
        dropdown = self.client.get(reverse("notifications_dropdown"))
        self.assertContains(dropdown, "liked your post")
        note = Notification.objects.filter(verb="comment").get()
        response = self.client.get(reverse("open_notification", args=[note.pk]))
        self.assertRedirects(
            response,
            f"{self.post.get_absolute_url()}#comment-{note.comment_id}",
            fetch_redirect_response=False,
        )
        note.refresh_from_db()
        self.assertTrue(note.is_read)
        self.client.post(reverse("notifications_read_all"), **FETCH)
        self.assertFalse(Notification.objects.filter(is_read=False).exists())

    def test_cannot_open_someone_elses_notification(self):
        services.set_reaction(self.post, self.fan, "like")
        self.login(self.fan)
        note = Notification.objects.get()
        self.assertEqual(self.client.get(reverse("open_notification", args=[note.pk])).status_code, 404)

    def test_notifications_page_paginates_and_marks_seen(self):
        for i in range(35):
            services.toggle_follow(make_user(f"f{i}"), self.owner)
        self.login(self.owner)
        response = self.client.get(reverse("notifications"))
        self.assertEqual(len(response.context["notifications"]), 30)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 5)


class DailyQuoteTests(QuickPostTestCase):
    def test_page_never_calls_gemini(self):
        user = make_user("reader")
        self.login(user)
        with mock.patch(
            "post.quotes.request_from_gemini", side_effect=AssertionError("network call during request")
        ):
            self.assertEqual(self.client.get(reverse("feed")).status_code, 200)
            self.assertEqual(self.client.get(reverse("home")).status_code, 302)

    def test_fallback_without_key_rotates_by_day(self):
        today = timezone.localdate()
        first = quotes.fallback_quote(today)
        second = quotes.fallback_quote(today + timedelta(days=1))
        self.assertNotEqual(first["text"], second["text"])
        self.assertEqual(quotes.current_quote()["source"], "fallback")

    def test_stored_quote_is_used_until_stale(self):
        DailyQuote.objects.create(text="Fresh words for today.", author="Vidura")
        self.assertEqual(quotes.current_quote()["author"], "Vidura")
        quotes.cache.clear()
        DailyQuote.objects.update(created_at=timezone.now() - timedelta(days=3))
        self.assertEqual(quotes.current_quote()["source"], "fallback")

    def test_cache_has_a_lifetime(self):
        with mock.patch("post.quotes.cache.set") as cache_set:
            quotes.current_quote()
        self.assertEqual(cache_set.call_args.args[2], quotes.CACHE_SECONDS)

    def test_refresh_success_and_failure(self):
        quotes.refresh_quote(fetch=lambda: '"Truth needs no armour." - Bhishma')
        self.assertEqual(DailyQuote.objects.get().author, "Bhishma")
        self.assertEqual(quotes.current_quote()["text"], "Truth needs no armour.")
        with self.assertRaises(quotes.QuoteUnavailable):
            quotes.refresh_quote(fetch=mock.Mock(side_effect=TimeoutError()))
        with self.assertRaises(quotes.QuoteUnavailable):
            quotes.refresh_quote(fetch=lambda: "no attribution here")
        self.assertEqual(DailyQuote.objects.count(), 1)
        self.assertEqual(quotes.current_quote()["author"], "Bhishma")

    def test_command_without_key_fails_cleanly(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.settings(GEMINI_API_KEY=""), self.assertRaises(CommandError):
            call_command("refresh_quote")
        with (
            self.settings(GEMINI_API_KEY="real-looking-key"),
            mock.patch("post.quotes.request_from_gemini", return_value="Stand firm in dharma. - Rama"),
        ):
            call_command("refresh_quote")
            call_command("refresh_quote", if_older_than=12)  # fresh: skipped
        self.assertEqual(DailyQuote.objects.count(), 1)


class LegacyUrlTests(QuickPostTestCase):
    def test_old_addresses_redirect(self):
        make_user("old")
        self.assertRedirects(self.client.get("/post/profile/old/"), "/u/old/", status_code=301)
        self.assertEqual(self.client.get("/post/").status_code, 301)


class ErrorPageTests(QuickPostTestCase):
    def test_custom_404_template(self):
        response = self.client.get("/definitely/not/here/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
