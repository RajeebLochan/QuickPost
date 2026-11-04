from django.db import migrations
from PIL import Image


def forwards(apps, schema_editor):
    """Preserve existing data while moving to the new schema."""
    Post = apps.get_model("post", "Post")
    PostImage = apps.get_model("post", "PostImage")
    UserProfile = apps.get_model("post", "UserProfile")
    Conversation = apps.get_model("post", "Conversation")
    Message = apps.get_model("post", "Message")

    # Single photos become the first image of the post (same file on disk).
    # Dimensions are read when the file is present; a missing file must not
    # stop the migration, it just leaves the dimensions empty.
    for post in Post.objects.exclude(photo="").exclude(photo__isnull=True).iterator():
        width = height = None
        try:
            with post.photo.open("rb") as handle, Image.open(handle) as img:
                width, height = img.size
        except (OSError, ValueError):
            pass
        PostImage.objects.create(post=post, image=post.photo.name, width=width, height=height, position=0)

    # The shared default avatar file is replaced by generated initials.
    UserProfile.objects.filter(profile_image="profile_pics/default.jpg").update(profile_image="")

    # Accounts that existed before email verification are treated as verified.
    UserProfile.objects.update(email_verified=True, onboarded=True)

    for conversation in Conversation.objects.iterator():
        last = Message.objects.filter(conversation=conversation).order_by("-created_at").first()
        if last:
            conversation.last_message_at = last.created_at
            conversation.save(update_fields=["last_message_at"])


def backwards(apps, schema_editor):
    Post = apps.get_model("post", "Post")
    PostImage = apps.get_model("post", "PostImage")
    for image in PostImage.objects.filter(position=0).iterator():
        Post.objects.filter(pk=image.post_id).update(photo=image.image.name)


class Migration(migrations.Migration):
    dependencies = [("post", "0011_social_platform")]

    operations = [migrations.RunPython(forwards, backwards)]
