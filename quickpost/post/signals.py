"""Model signal handlers: profile creation and media cleanup."""

import logging

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import PostImage, UserProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, raw=False, **kwargs):
    """Every user gets exactly one profile. Never touches image files."""
    if created and not raw:
        UserProfile.objects.get_or_create(user=instance)


def _delete_file_later(field_file):
    if not field_file or not field_file.name:
        return
    storage, name = field_file.storage, field_file.name

    def _delete():
        try:
            storage.delete(name)
        except OSError:
            logger.warning("event=media_delete_failed file=%s", name)

    transaction.on_commit(_delete)


@receiver(post_delete, sender=PostImage)
def delete_post_image_file(sender, instance, **kwargs):
    _delete_file_later(instance.image)


@receiver(post_delete, sender=UserProfile)
def delete_profile_files(sender, instance, **kwargs):
    _delete_file_later(instance.profile_image)
    _delete_file_later(instance.cover_image)


@receiver(pre_save, sender=UserProfile)
def delete_replaced_profile_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = UserProfile.objects.only("profile_image", "cover_image").get(pk=instance.pk)
    except UserProfile.DoesNotExist:
        return
    for field in ("profile_image", "cover_image"):
        old_file = getattr(old, field)
        if old_file and old_file.name != getattr(instance, field).name:
            _delete_file_later(old_file)
