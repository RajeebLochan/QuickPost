from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from post import services
from post.models import Comment, Post, PostImage

from .base import FETCH, QuickPostTestCase, image_file, make_user, quickpost_settings


class PostCreateTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user("author")
        self.login(self.user)

    def test_create_text_post_with_hashtags_and_mentions(self):
        friend = make_user("friend")
        response = self.client.post(reverse("compose"), {"content": "Hello @friend #Monsoon #art"})
        self.assertRedirects(response, reverse("feed"))
        post = Post.objects.get(user=self.user)
        self.assertEqual(set(post.hashtags.values_list("name", flat=True)), {"monsoon", "art"})
        self.assertEqual(list(post.mentions.all()), [friend])
        self.assertTrue(friend.notifications.filter(verb="mention", post=post).exists())

    def test_create_post_with_multiple_images_strips_metadata_and_resizes(self):
        exif = Image.Exif()
        exif[0x010F] = "Camera Maker"  # Make
        images = [image_file("big.jpg", (3000, 1000), exif=exif), image_file("b.png", (40, 40), "PNG")]
        response = self.client.post(reverse("compose"), {"content": "", "images": images})
        self.assertRedirects(response, reverse("feed"))
        post = Post.objects.get(user=self.user)
        stored = list(post.images.all())
        self.assertEqual(len(stored), 2)
        self.assertEqual(stored[0].width, 2048)
        with Image.open(stored[0].image.path) as img:
            self.assertFalse(img.getexif())

    def test_too_many_images_rejected(self):
        response = self.client.post(
            reverse("compose"), {"content": "x", "images": [image_file(f"{i}.jpg") for i in range(5)]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_non_image_and_oversized_upload_rejected(self):
        fake = SimpleUploadedFile("evil.png", b"not an image", content_type="image/png")
        response = self.client.post(reverse("compose"), {"content": "x", "images": [fake]})
        self.assertEqual(response.status_code, 200)
        with quickpost_settings(MAX_IMAGE_BYTES=100):
            response = self.client.post(reverse("compose"), {"content": "x", "images": [image_file()]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_empty_and_too_long_posts_rejected(self):
        self.client.post(reverse("compose"), {"content": "   "})
        self.client.post(reverse("compose"), {"content": "x" * 241})
        self.assertFalse(Post.objects.exists())
        response = self.client.post(reverse("compose"), {"content": ""}, **FETCH)
        self.assertEqual(response.status_code, 400)

    def test_compose_is_rate_limited(self):
        statuses = [
            self.client.post(reverse("compose"), {"content": f"post {i}"}).status_code for i in range(11)
        ]
        self.assertEqual(statuses[-1], 429)
        self.assertEqual(Post.objects.count(), 10)


class PostPermissionTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner")
        self.other = make_user("other")
        self.post = self.post_as(self.owner, "original text")

    def test_owner_can_edit(self):
        self.login(self.owner)
        response = self.client.post(reverse("post_edit", args=[self.post.pk]), {"content": "edited #new"})
        self.assertRedirects(response, self.post.get_absolute_url())
        self.post.refresh_from_db()
        self.assertEqual(self.post.content, "edited #new")
        self.assertIsNotNone(self.post.edited_at)
        self.assertEqual(list(self.post.hashtags.values_list("name", flat=True)), ["new"])

    def test_others_get_403_on_edit_and_delete(self):
        self.login(self.other)
        self.assertEqual(self.client.get(reverse("post_edit", args=[self.post.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("post_edit", args=[self.post.pk]), {"content": "x"}).status_code, 403
        )
        self.assertEqual(self.client.post(reverse("post_delete", args=[self.post.pk])).status_code, 403)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_owner_can_delete_and_images_are_removed(self):
        post = self.post_as(self.owner, "with image", images=[image_file()])
        path = post.images.first().image.path
        self.login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("post_delete", args=[post.pk]), **FETCH)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())
        import os

        self.assertFalse(os.path.exists(path))

    def test_missing_image_file_does_not_break_pages(self):
        post = self.post_as(self.owner, "photo gone", images=[image_file()])
        PostImage.objects.filter(post=post).update(image="posts/2020/01/missing.jpg", width=None, height=None)
        self.login(self.other)
        services.toggle_follow(self.other, self.owner)
        self.assertEqual(self.client.get(reverse("feed")).status_code, 200)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 200)

    def test_missing_objects_return_404(self):
        self.login(self.other)
        for url in (
            reverse("post_detail", args=[9999]),
            reverse("post_edit", args=[9999]),
            reverse("profile", args=["nobody"]),
            reverse("hashtag", args=["nothing"]),
            reverse("chat_room", args=[9999]),
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for url in (
            reverse("post_react", args=[9999, "like"]),
            reverse("comment_create", args=[9999]),
            reverse("comment_delete", args=[9999]),
            reverse("post_repost", args=[9999]),
            reverse("post_save", args=[9999]),
            reverse("toggle_follow", args=["nobody"]),
        ):
            self.assertEqual(self.client.post(url, {"content": "x"}, **FETCH).status_code, 404, url)

    def test_actions_require_post(self):
        self.login(self.other)
        for url in (
            reverse("post_react", args=[self.post.pk, "like"]),
            reverse("post_repost", args=[self.post.pk]),
            reverse("toggle_follow", args=["owner"]),
            reverse("message_user", args=["owner"]),
            reverse("comment_create", args=[self.post.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 405, url)


class ReactionTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner")
        self.fan = make_user("fan")
        self.post = self.post_as(self.owner)
        self.login(self.fan)

    def react(self, kind):
        response = self.client.post(reverse("post_react", args=[self.post.pk, kind]), **FETCH)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_like_toggle(self):
        self.assertEqual(
            self.react("like"), {"liked": True, "disliked": False, "likes_count": 1, "dislikes_count": 0}
        )
        self.assertEqual(self.react("like")["liked"], False)
        self.assertEqual(self.post.likes.count(), 0)

    def test_like_and_dislike_are_mutually_exclusive(self):
        self.react("dislike")
        data = self.react("like")
        self.assertEqual((data["liked"], data["disliked"]), (True, False))
        data = self.react("dislike")
        self.assertEqual((data["liked"], data["disliked"]), (False, True))
        self.assertFalse(self.post.likes.filter(pk=self.fan.pk).exists())
        self.assertTrue(self.post.dislikes.filter(pk=self.fan.pk).exists())

    def test_unknown_reaction_is_400(self):
        response = self.client.post(reverse("post_react", args=[self.post.pk, "love"]), **FETCH)
        self.assertEqual(response.status_code, 400)

    def test_like_without_js_redirects_back(self):
        response = self.client.post(reverse("post_react", args=[self.post.pk, "like"]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.post.likes.filter(pk=self.fan.pk).exists())


class RepostAndBookmarkTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner")
        self.fan = make_user("fan")
        self.post = self.post_as(self.owner, "share me")
        self.login(self.fan)

    def test_repost_toggle(self):
        data = self.client.post(reverse("post_repost", args=[self.post.pk]), **FETCH).json()
        self.assertEqual((data["reposted"], data["reposts_count"]), (True, 1))
        repost = Post.objects.get(user=self.fan)
        self.assertEqual(repost.repost_of, self.post)
        # Reposting the repost targets the original and undoes it.
        data = self.client.post(reverse("post_repost", args=[repost.pk]), **FETCH).json()
        self.assertEqual((data["reposted"], data["reposts_count"]), (False, 0))

    def test_quote_post(self):
        response = self.client.post(reverse("compose"), {"content": "So true", "quote_of": self.post.pk})
        self.assertRedirects(response, reverse("feed"))
        quote = Post.objects.get(user=self.fan)
        self.assertEqual((quote.repost_of, quote.content), (self.post, "So true"))
        self.assertEqual(self.client.get(quote.get_absolute_url()).status_code, 200)

    def test_cannot_repost_own_or_private_posts(self):
        own = self.post_as(self.fan, "mine")
        self.assertEqual(self.client.post(reverse("post_repost", args=[own.pk]), **FETCH).status_code, 400)
        private_owner = make_user("secret", private=True)
        services.toggle_follow(self.fan, private_owner)
        services.respond_to_follow_request(private_owner.follow_requests.get(), private_owner, accept=True)
        private_post = self.post_as(private_owner, "only friends")
        response = self.client.post(reverse("post_repost", args=[private_post.pk]), **FETCH)
        self.assertEqual(response.status_code, 400)

    def test_bookmark_and_saved_page(self):
        data = self.client.post(reverse("post_save", args=[self.post.pk]), **FETCH).json()
        self.assertTrue(data["saved"])
        response = self.client.get(reverse("saved"))
        self.assertContains(response, "share me")
        data = self.client.post(reverse("post_save", args=[self.post.pk]), **FETCH).json()
        self.assertFalse(data["saved"])


class CommentTests(QuickPostTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner")
        self.commenter = make_user("commenter")
        self.stranger = make_user("stranger")
        self.post = self.post_as(self.owner)

    def comment(self, user, content, parent=None):
        self.client.force_login(user)
        data = {"content": content}
        if parent:
            data["parent"] = parent
        return self.client.post(reverse("comment_create", args=[self.post.pk]), data, **FETCH)

    def test_create_comment_returns_rendered_html(self):
        response = self.comment(self.commenter, "Nice <b>post</b>")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["comments_count"], 1)
        self.assertIn("Nice &lt;b&gt;post&lt;/b&gt;", data["html"])
        self.assertTrue(self.owner.notifications.filter(verb="comment").exists())

    def test_comment_validation(self):
        self.assertEqual(self.comment(self.commenter, "").status_code, 400)
        self.client.force_login(self.commenter)
        missing = self.client.post(reverse("comment_create", args=[self.post.pk]), {}, **FETCH)
        self.assertEqual(missing.status_code, 400)
        self.assertIn("can't be empty", missing.json()["error"])
        too_long = self.comment(self.commenter, "x" * 501)
        self.assertEqual(too_long.status_code, 400)
        self.assertIn("500", too_long.json()["error"])
        self.assertEqual(self.comment(self.commenter, "x" * 500).status_code, 200)
        self.assertEqual(Comment.objects.count(), 1)

    def test_replies_are_one_level_and_notify_parent_author(self):
        top = Comment.objects.get(pk=self.comment(self.commenter, "first").json()["id"])
        reply = self.comment(self.stranger, "@commenter agreed", parent=top.pk).json()
        nested = self.comment(self.owner, "thanks", parent=reply["id"]).json()
        self.assertEqual(Comment.objects.get(pk=nested["id"]).parent_id, top.pk)
        self.assertTrue(self.commenter.notifications.filter(verb="reply").exists())

    def test_reply_parent_must_belong_to_post(self):
        other_post = self.post_as(self.owner, "another")
        foreign = services.add_comment(other_post, self.owner, "elsewhere")
        response = self.comment(self.commenter, "x", parent=foreign.pk)
        self.assertEqual(response.status_code, 404)

    def test_comment_deletion_authorization(self):
        comment_id = self.comment(self.commenter, "mine").json()["id"]
        self.client.force_login(self.stranger)
        self.assertEqual(
            self.client.post(reverse("comment_delete", args=[comment_id]), **FETCH).status_code, 403
        )
        self.client.force_login(self.commenter)
        self.assertEqual(
            self.client.post(reverse("comment_delete", args=[comment_id]), **FETCH).status_code, 200
        )
        # The post owner can moderate comments on their post.
        comment_id = self.comment(self.stranger, "rude").json()["id"]
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(reverse("comment_delete", args=[comment_id]), **FETCH).status_code, 200
        )
        self.assertFalse(Comment.objects.exists())

    def test_comment_spam_rate_limit(self):
        statuses = [self.comment(self.commenter, f"c{i}").status_code for i in range(21)]
        self.assertEqual(statuses[-1], 429)

    def test_comments_paginate(self):
        for i in range(25):
            services.add_comment(self.post, self.commenter, f"comment {i}")
        self.client.force_login(self.owner)
        page1 = self.client.get(reverse("post_detail", args=[self.post.pk]))
        self.assertEqual(len(page1.context["comments"]), 20)
        page2 = self.client.get(reverse("comments_list", args=[self.post.pk]) + "?page=2&partial=1").json()
        self.assertFalse(page2["has_next"])
        self.assertIn("comment 24", page2["html"])


class RichTextTests(QuickPostTestCase):
    def test_escapes_and_links(self):
        from post.templatetags.quickpost import rich_text

        html = rich_text("<script>x</script> it's #Tag @meera https://example.com/a?b=1&c=2")
        self.assertNotIn("<script>", html)
        self.assertIn('href="/tags/tag/"', html)
        self.assertIn('href="/u/meera/"', html)
        self.assertIn('href="https://example.com/a?b=1&amp;c=2"', html)
        self.assertNotIn("#x27", html.replace("&#x27;", ""))  # apostrophe entity is not a hashtag
