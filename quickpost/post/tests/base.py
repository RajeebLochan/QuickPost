import io
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from post import services

TEMP_MEDIA = tempfile.mkdtemp(prefix="quickpost-test-media-")


def make_user(username, *, verified=True, private=False, password="pass-12345!", **profile):
    user = User.objects.create_user(username, f"{username}@example.com", password)
    p = user.profile
    p.email_verified = verified
    p.is_private = private
    for key, value in profile.items():
        setattr(p, key, value)
    p.save()
    return user


def image_file(name="photo.jpg", size=(64, 48), fmt="JPEG", color=(200, 80, 60), exif=None):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(buf, fmt, **kwargs)
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, buf.getvalue(), content_type=content_type)


FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class QuickPostTestCase(TestCase):
    """Base class: temp media, clean cache (rate limits, quotes) per test."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()

    def login(self, user, password="pass-12345!"):
        self.assertTrue(self.client.login(username=user.username, password=password))

    def post_as(self, user, content="hello world", **kwargs):
        return services.create_post(user, content, **kwargs)


def quickpost_settings(**overrides):
    return override_settings(QUICKPOST={**settings.QUICKPOST, **overrides})
