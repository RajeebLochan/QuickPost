import re

from django.contrib.auth.models import User
from django.core import mail, signing
from django.urls import reverse

from post import services
from post.emails import make_verification_token
from post.models import UserProfile

from .base import QuickPostTestCase, image_file, make_user, quickpost_settings


class RegistrationTests(QuickPostTestCase):
    def test_register_creates_one_profile_logs_in_and_sends_verification(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "new.user",
                "email": "New@Example.com",
                "password1": "a-long-pass-123",
                "password2": "a-long-pass-123",
            },
        )
        self.assertRedirects(response, reverse("onboarding"))
        user = User.objects.get(username="new.user")
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)
        self.assertFalse(user.profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/verify/", mail.outbox[0].body)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_username_uniqueness_is_case_insensitive_and_validated(self):
        make_user("Meera")
        for username in ("meera", "x", "bad name", "admin"):
            response = self.client.post(
                reverse("register"),
                {
                    "username": username,
                    "email": f"{len(username)}@ex.com",
                    "password1": "a-long-pass-123",
                    "password2": "a-long-pass-123",
                },
            )
            self.assertEqual(response.status_code, 200, username)
            self.assertTrue(response.context["form"].errors.get("username"), username)

    def test_duplicate_email_rejected(self):
        make_user("first")
        response = self.client.post(
            reverse("register"),
            {
                "username": "second",
                "email": "FIRST@example.com",
                "password1": "a-long-pass-123",
                "password2": "a-long-pass-123",
            },
        )
        self.assertIn("email", response.context["form"].errors)

    def test_verification_link(self):
        user = make_user("ver", verified=False)
        response = self.client.get(reverse("verify_email", args=[make_verification_token(user)]))
        self.assertEqual(response.status_code, 200)
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.email_verified)

    def test_bad_and_stale_verification_links(self):
        user = make_user("ver2", verified=False)
        self.assertEqual(self.client.get(reverse("verify_email", args=["garbage"])).status_code, 400)
        token = make_verification_token(user)
        user.email = "changed@example.com"
        user.save()
        self.assertEqual(self.client.get(reverse("verify_email", args=[token])).status_code, 400)
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.email_verified)

    def test_unverified_users_cannot_post(self):
        user = make_user("unverified", verified=False)
        self.login(user)
        response = self.client.post(reverse("compose"), {"content": "hi"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(response.status_code, 403)

    @quickpost_settings(REQUIRE_EMAIL_VERIFICATION=False)
    def test_verification_requirement_can_be_disabled(self):
        user = make_user("unverified2", verified=False)
        self.login(user)
        response = self.client.post(reverse("compose"), {"content": "hi"})
        self.assertRedirects(response, reverse("feed"))


class LoginTests(QuickPostTestCase):
    def test_login_and_logout(self):
        user = make_user("loginuser")
        response = self.client.post(reverse("login"), {"username": "loginuser", "password": "pass-12345!"})
        self.assertRedirects(response, reverse("feed"), fetch_redirect_response=False)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(user.is_active)

    def test_wrong_password(self):
        make_user("loginuser2")
        response = self.client.post(reverse("login"), {"username": "loginuser2", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "don&#x27;t match")

    def test_missing_avatar_file_does_not_break_login(self):
        user = make_user("ghost")
        UserProfile.objects.filter(user=user).update(profile_image="avatars/2020/01/missing.jpg")
        response = self.client.post(reverse("login"), {"username": "ghost", "password": "pass-12345!"})
        self.assertEqual(response.status_code, 302)
        # And pages that render the avatar still work.
        self.assertEqual(self.client.get(reverse("feed")).status_code, 200)

    def test_login_is_rate_limited(self):
        make_user("target")
        statuses = [
            self.client.post(reverse("login"), {"username": "target", "password": "wrong"}).status_code
            for _ in range(12)
        ]
        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[-1], 429)

    def test_protected_routes_redirect_to_login(self):
        for name in ("feed", "explore", "notifications", "inbox", "saved", "settings_profile"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("login"), response["Location"])

    def test_password_reset_sends_email(self):
        make_user("forgetful")
        response = self.client.post(reverse("password_reset"), {"email": "forgetful@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://\S+", mail.outbox[0].body).group(0)
        response = self.client.get(link, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["validlink"])


class AccountLifecycleTests(QuickPostTestCase):
    def test_deactivate_hides_account_and_login_restores_it(self):
        user = make_user("pause")
        other = make_user("viewer")
        post = self.post_as(user, "still here")
        self.login(user)
        response = self.client.post(reverse("deactivate_account"), {"password": "pass-12345!"})
        self.assertRedirects(response, reverse("home"))
        self.client.logout()
        self.login(other)
        self.assertEqual(self.client.get(reverse("profile", args=["pause"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("post_detail", args=[post.pk])).status_code, 404)
        self.client.logout()
        self.client.post(reverse("login"), {"username": "pause", "password": "pass-12345!"})
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.is_deactivated)

    def test_deactivate_requires_password(self):
        user = make_user("keep")
        self.login(user)
        self.client.post(reverse("deactivate_account"), {"password": "wrong"})
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.is_deactivated)

    def test_delete_account_requires_password_and_username(self):
        user = make_user("leaving")
        self.post_as(user, "bye", images=[image_file()])
        self.login(user)
        response = self.client.post(
            reverse("delete_account"), {"password": "pass-12345!", "confirm_username": "nope"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="leaving").exists())
        response = self.client.post(
            reverse("delete_account"), {"password": "pass-12345!", "confirm_username": "leaving"}
        )
        self.assertRedirects(response, reverse("home"))
        self.assertFalse(User.objects.filter(username="leaving").exists())

    def test_changing_email_requires_reverification(self):
        user = make_user("mover")
        self.login(user)
        self.client.post(reverse("settings_account"), {"username": "mover", "email": "new@example.com"})
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)


class ProfileEditTests(QuickPostTestCase):
    def test_edit_profile_with_avatar(self):
        user = make_user("painter")
        self.login(user)
        response = self.client.post(
            reverse("settings_profile"),
            {
                "display_name": "Meera Iyer",
                "bio": "Illustrator",
                "location": "Pune",
                "website": "https://example.com",
                "profile_image": image_file("a.png", (900, 600), "PNG"),
            },
        )
        self.assertRedirects(response, reverse("profile", args=["painter"]))
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.display_name, "Meera Iyer")
        self.assertTrue(user.profile.profile_image.name.startswith("avatars/"))
        from PIL import Image

        with Image.open(user.profile.profile_image.path) as img:
            self.assertLessEqual(max(img.size), 400)

    def test_rejects_non_image_avatar(self):
        user = make_user("hacker")
        self.login(user)
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile("x.jpg", b"<?php echo 1; ?>", content_type="image/jpeg")
        response = self.client.post(reverse("settings_profile"), {"display_name": "x", "profile_image": fake})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("profile_image"))

    def test_private_to_public_approves_pending_requests(self):
        owner = make_user("owner", private=True)
        fan = make_user("fan")
        services.toggle_follow(fan, owner)
        self.login(owner)
        self.client.post(reverse("settings_privacy"), {})
        self.assertTrue(fan.profile.following.filter(pk=owner.profile.pk).exists())


class SigningTests(QuickPostTestCase):
    def test_expired_token(self):
        user = make_user("old", verified=False)
        token = make_verification_token(user)
        with self.settings():
            from unittest import mock

            with mock.patch("post.emails.signing.loads", side_effect=signing.SignatureExpired("old")):
                response = self.client.get(reverse("verify_email", args=[token]))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "expired", status_code=400)
