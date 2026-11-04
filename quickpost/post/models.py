import uuid
from pathlib import PurePath

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

POST_MAX_LENGTH = 240
COMMENT_MAX_LENGTH = 500
MESSAGE_MAX_LENGTH = 1000


def _uuid_path(folder, filename):
    suffix = PurePath(filename).suffix.lower()[:5] or ".jpg"
    return f"{folder}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{suffix}"


def avatar_upload_to(instance, filename):
    return _uuid_path("avatars", filename)


def cover_upload_to(instance, filename):
    return _uuid_path("covers", filename)


def post_image_upload_to(instance, filename):
    return _uuid_path("posts", filename)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=50, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    profile_image = models.ImageField(upload_to=avatar_upload_to, blank=True)
    cover_image = models.ImageField(upload_to=cover_upload_to, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=200, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    is_private = models.BooleanField(default=False, help_text="Only approved followers can see posts.")
    email_verified = models.BooleanField(default=False)
    onboarded = models.BooleanField(default=False)
    is_deactivated = models.BooleanField(default=False)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    following = models.ManyToManyField("self", symmetrical=False, related_name="followers", blank=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

    def get_absolute_url(self):
        return reverse("profile", args=[self.user.username])

    @property
    def name(self):
        return self.display_name or self.user.get_full_name() or self.user.username

    @property
    def avatar_url(self):
        return self.profile_image.url if self.profile_image else ""

    @property
    def initial(self):
        return (self.name or "?")[:1].upper()

    def is_following(self, other_profile):
        return self.following.filter(pk=other_profile.pk).exists()


class Hashtag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"#{self.name}"

    def get_absolute_url(self):
        return reverse("hashtag", args=[self.name])


class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    content = models.TextField(max_length=POST_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    likes = models.ManyToManyField(User, related_name="liked_posts", blank=True)
    dislikes = models.ManyToManyField(User, related_name="disliked_posts", blank=True)
    repost_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="reposts"
    )
    hashtags = models.ManyToManyField(Hashtag, related_name="posts", blank=True)
    mentions = models.ManyToManyField(User, related_name="mentioned_in", blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"], name="post_user_created_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "repost_of"],
                condition=Q(repost_of__isnull=False, content=""),
                name="unique_plain_repost",
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.content[:20]}"

    def get_absolute_url(self):
        return reverse("post_detail", args=[self.pk])

    @property
    def is_plain_repost(self):
        return self.repost_of_id is not None and not self.content


class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    # Dimensions are recorded when the upload is processed (see services.create_post).
    # No width_field/height_field: Django would open the file on every row load,
    # and a missing file would then break whole pages.
    image = models.ImageField(upload_to=post_image_upload_to)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    alt_text = models.CharField(max_length=200, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"Image {self.position} of post {self.post_id}"


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField(max_length=COMMENT_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["post", "parent", "created_at"], name="comment_thread_idx")]

    def __str__(self):
        return f"{self.user.username}: {self.content[:20]}"

    def get_absolute_url(self):
        return f"{self.post.get_absolute_url()}#comment-{self.pk}"


class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookmarks")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_bookmark")]

    def __str__(self):
        return f"{self.user} saved post {self.post_id}"


class FollowRequest(models.Model):
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_follow_requests")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follow_requests")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="unique_follow_request"),
            models.CheckConstraint(
                condition=~Q(from_user=models.F("to_user")), name="follow_request_not_self"
            ),
        ]

    def __str__(self):
        return f"{self.from_user} -> {self.to_user}"


class Block(models.Model):
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocks_made")
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocks_received")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_block"),
            models.CheckConstraint(condition=~Q(blocker=models.F("blocked")), name="block_not_self"),
        ]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment or bullying"
        HATE = "hate", "Hate speech"
        VIOLENCE = "violence", "Violence or threats"
        NUDITY = "nudity", "Nudity or sexual content"
        IMPERSONATION = "impersonation", "Impersonation"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACTIONED = "actioned", "Action taken"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reports_made")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField(max_length=1000, blank=True)
    post = models.ForeignKey(Post, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    comment = models.ForeignKey(
        Comment, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports"
    )
    reported_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="reports_received"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolution_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report #{self.pk} ({self.get_reason_display()})"


class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name="conversations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation {self.pk}"

    def get_absolute_url(self):
        return reverse("chat_room", args=[self.pk])

    def get_other_participant(self, user):
        for participant in self.participants.all():
            if participant.pk != user.pk:
                return participant
        return None


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    content = models.TextField(max_length=MESSAGE_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="message_conv_created_idx"),
            models.Index(fields=["conversation", "is_read"], name="message_conv_unread_idx"),
        ]

    def __str__(self):
        return f"Message from {self.sender.username}: {self.content[:30]}"

    def as_payload(self):
        return {
            "id": self.pk,
            "conversation": self.conversation_id,
            "content": self.content,
            "sender": self.sender.username,
            "sender_id": self.sender_id,
            "timestamp": self.created_at.isoformat(),
            "is_read": self.is_read,
        }


class Notification(models.Model):
    class Verb(models.TextChoices):
        FOLLOW = "follow", "followed you"
        FOLLOW_REQUEST = "follow_request", "asked to follow you"
        FOLLOW_ACCEPT = "follow_accept", "accepted your follow request"
        LIKE = "like", "liked your post"
        COMMENT = "comment", "commented on your post"
        REPLY = "reply", "replied to your comment"
        MENTION = "mention", "mentioned you"
        REPOST = "repost", "reposted your post"
        MESSAGE = "message", "sent you a message"

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications_sent")
    verb = models.CharField(max_length=20, choices=Verb.choices)
    post = models.ForeignKey(Post, null=True, blank=True, on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, null=True, blank=True, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, null=True, blank=True, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"], name="notif_recipient_idx")]

    def __str__(self):
        return f"{self.actor} {self.get_verb_display()}"

    @property
    def target_url(self):
        if self.verb == self.Verb.MESSAGE and self.conversation_id:
            return reverse("chat_room", args=[self.conversation_id])
        if self.verb == self.Verb.FOLLOW_REQUEST:
            return reverse("follow_requests")
        if self.comment_id:
            return f"{reverse('post_detail', args=[self.post_id])}#comment-{self.comment_id}"
        if self.post_id:
            return reverse("post_detail", args=[self.post_id])
        return reverse("profile", args=[self.actor.username])


class DailyQuote(models.Model):
    class Source(models.TextChoices):
        GEMINI = "gemini", "Gemini"
        MANUAL = "manual", "Manual"

    text = models.CharField(max_length=300)
    author = models.CharField(max_length=60)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.GEMINI)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.text} - {self.author}"
