"""Write-side business logic.

Views and the WebSocket consumer call these functions; they own validation,
permissions, transactions, notifications and real-time pushes. Errors are
raised as `ValidationError` (bad input, HTTP 400), `PermissionDenied`
(HTTP 403) or `ServiceError` (a rule was broken, HTTP 400).
"""

import logging
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import realtime, selectors
from .models import (
    COMMENT_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    POST_MAX_LENGTH,
    Block,
    Bookmark,
    Comment,
    Conversation,
    FollowRequest,
    Hashtag,
    Message,
    Notification,
    Post,
    PostImage,
    Report,
    UserProfile,
)
from .uploads import POST_IMAGE_SIZE, process_image

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"(?<![\w&/])#(\w{1,50})")
MENTION_RE = re.compile(r"(?<![\w@/])@([\w.+-]{1,150})")

Verb = Notification.Verb


class ServiceError(Exception):
    """A request that is well-formed but not allowed by a product rule."""


# ---------------------------------------------------------------- parsing


def extract_hashtags(text):
    return {tag.lower() for tag in HASHTAG_RE.findall(text or "")}


def extract_mentions(text):
    return {name.rstrip(".-+") for name in MENTION_RE.findall(text or "") if name.rstrip(".-+")}


def clean_text(value, max_length, label, allow_empty=False):
    text = (value or "").strip()
    if not text and not allow_empty:
        raise ValidationError(f"{label} can't be empty.", code="empty")
    if len(text) > max_length:
        raise ValidationError(
            f"{label} can be at most {max_length} characters ({len(text)} entered).", code="too_long"
        )
    return text


# ---------------------------------------------------------------- notifications


def notify(recipient, actor, verb, *, post=None, comment=None, conversation=None):
    if recipient.pk == actor.pk or selectors.is_blocked_between(recipient, actor):
        return None
    notification = Notification.objects.create(
        recipient=recipient, actor=actor, verb=verb, post=post, comment=comment, conversation=conversation
    )
    if verb != Verb.MESSAGE:
        realtime.push_on_commit(
            [recipient.pk],
            {
                "type": "notification",
                "id": notification.pk,
                "actor": actor.username,
                "text": f"{actor.profile.name} {notification.get_verb_display()}",
                "url": notification.target_url,
            },
        )
    return notification


def _withdraw(recipient, actor, verb, **targets):
    Notification.objects.filter(
        recipient=recipient, actor=actor, verb=verb, is_read=False, **targets
    ).delete()


def mark_notifications_read(user, ids=None):
    qs = Notification.objects.filter(recipient=user, is_read=False)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return qs.update(is_read=True)


# ---------------------------------------------------------------- posts


def _sync_tags_and_mentions(post, notify_new=True):
    names = extract_hashtags(post.content)
    if names:
        Hashtag.objects.bulk_create([Hashtag(name=n) for n in names], ignore_conflicts=True)
    post.hashtags.set(Hashtag.objects.filter(name__in=names))

    usernames = extract_mentions(post.content)
    mentioned = list(
        selectors.active_users(post.user).filter(username__in=usernames).exclude(pk=post.user_id)
    )
    previous = set(post.mentions.values_list("pk", flat=True))
    post.mentions.set(mentioned)
    if notify_new:
        for user in mentioned:
            if user.pk not in previous and selectors.can_view_posts(user, post.user):
                notify(user, post.user, Verb.MENTION, post=post)


@transaction.atomic
def create_post(author, content, images=(), repost_of=None):
    images = list(images)
    max_images = settings.QUICKPOST["MAX_IMAGES_PER_POST"]
    if len(images) > max_images:
        raise ValidationError(f"Add at most {max_images} images.", code="too_many_images")
    text = clean_text(content, POST_MAX_LENGTH, "Post", allow_empty=bool(images) or repost_of is not None)
    if repost_of is not None:
        _check_repostable(repost_of, author)
    processed = [process_image(upload, POST_IMAGE_SIZE) for upload in images]
    post = Post.objects.create(user=author, content=text, repost_of=repost_of)
    for position, image_file in enumerate(processed):
        width, height = image_file.image_size
        PostImage.objects.create(post=post, image=image_file, width=width, height=height, position=position)
    _sync_tags_and_mentions(post)
    if repost_of is not None:
        notify(repost_of.user, author, Verb.REPOST, post=repost_of)
    logger.info("event=post_created post=%s user=%s images=%s", post.pk, author.pk, len(processed))
    return post


@transaction.atomic
def edit_post(post, editor, content):
    if post.user_id != editor.pk:
        raise PermissionDenied("You can only edit your own posts.")
    if post.is_plain_repost:
        raise ServiceError("Reposts can't be edited.")
    has_images = post.images.exists()
    post.content = clean_text(
        content, POST_MAX_LENGTH, "Post", allow_empty=has_images or post.repost_of_id is not None
    )
    post.edited_at = timezone.now()
    post.save(update_fields=["content", "edited_at", "updated_at"])
    _sync_tags_and_mentions(post)
    return post


def delete_post(post, user):
    if post.user_id != user.pk and not user.is_staff:
        raise PermissionDenied("You can only delete your own posts.")
    logger.info("event=post_deleted post=%s by=%s", post.pk, user.pk)
    post.delete()


@transaction.atomic
def set_reaction(post, user, kind):
    """Toggle a like or dislike. Likes and dislikes are mutually exclusive."""
    if kind not in ("like", "dislike"):
        raise ValidationError("Unknown reaction.", code="invalid")
    liked = post.likes.filter(pk=user.pk).exists()
    disliked = post.dislikes.filter(pk=user.pk).exists()

    if kind == "like":
        if liked:
            post.likes.remove(user)
            liked = False
            _withdraw(post.user, user, Verb.LIKE, post=post)
        else:
            post.likes.add(user)
            post.dislikes.remove(user)
            liked, disliked = True, False
            if not Notification.objects.filter(
                recipient=post.user, actor=user, verb=Verb.LIKE, post=post
            ).exists():
                notify(post.user, user, Verb.LIKE, post=post)
    else:
        if disliked:
            post.dislikes.remove(user)
            disliked = False
        else:
            post.dislikes.add(user)
            if liked:
                post.likes.remove(user)
                _withdraw(post.user, user, Verb.LIKE, post=post)
            liked, disliked = False, True

    return {
        "liked": liked,
        "disliked": disliked,
        "likes_count": post.likes.count(),
        "dislikes_count": post.dislikes.count(),
    }


def _check_repostable(original, user):
    if original.user_id == user.pk:
        raise ServiceError("You can't repost your own post.")
    if original.user.profile.is_private:
        raise ServiceError("Posts from private accounts can't be reposted.")


@transaction.atomic
def toggle_repost(post, user):
    original = post.repost_of if post.is_plain_repost else post
    _check_repostable(original, user)
    existing = Post.objects.filter(user=user, repost_of=original, content="").first()
    if existing:
        existing.delete()
        _withdraw(original.user, user, Verb.REPOST, post=original)
        reposted = False
    else:
        try:
            with transaction.atomic():
                Post.objects.create(user=user, repost_of=original, content="")
        except IntegrityError:
            pass  # A concurrent request created it first; the end state is the same.
        notify(original.user, user, Verb.REPOST, post=original)
        reposted = True
    return {
        "reposted": reposted,
        "reposts_count": Post.objects.filter(repost_of=original).count(),
        "original_id": original.pk,
    }


def toggle_bookmark(post, user):
    deleted, _ = Bookmark.objects.filter(user=user, post=post).delete()
    if deleted:
        return {"saved": False}
    Bookmark.objects.get_or_create(user=user, post=post)
    return {"saved": True}


# ---------------------------------------------------------------- comments


@transaction.atomic
def add_comment(post, user, content, parent=None):
    text = clean_text(content, COMMENT_MAX_LENGTH, "Comment")
    if selectors.is_blocked_between(user, post.user):
        raise PermissionDenied("You can't comment on this post.")
    if parent is not None:
        if parent.post_id != post.pk:
            raise ValidationError("That reply doesn't belong to this post.", code="invalid_parent")
        if parent.parent_id:  # keep threads one level deep
            parent = parent.parent
    comment = Comment.objects.create(post=post, user=user, content=text, parent=parent)

    notified = {user.pk}
    if parent is not None and parent.user_id not in notified:
        notify(parent.user, user, Verb.REPLY, post=post, comment=comment)
        notified.add(parent.user_id)
    if post.user_id not in notified:
        notify(post.user, user, Verb.COMMENT, post=post, comment=comment)
        notified.add(post.user_id)
    for mentioned in selectors.active_users(user).filter(username__in=extract_mentions(text)):
        if mentioned.pk not in notified and selectors.can_view_posts(mentioned, post.user):
            notify(mentioned, user, Verb.MENTION, post=post, comment=comment)
            notified.add(mentioned.pk)
    return comment


def can_delete_comment(comment, user):
    return user.is_authenticated and (
        comment.user_id == user.pk or comment.post.user_id == user.pk or user.is_staff
    )


def delete_comment(comment, user):
    if not can_delete_comment(comment, user):
        raise PermissionDenied("You can't delete this comment.")
    comment.delete()


# ---------------------------------------------------------------- follows


def _profiles(*users):
    return [UserProfile.objects.get_or_create(user=u)[0] for u in users]


@transaction.atomic
def toggle_follow(actor, target):
    """Follow, unfollow, request or cancel a request. Returns the new state."""
    if actor.pk == target.pk:
        raise ServiceError("You can't follow yourself.")
    if selectors.is_blocked_between(actor, target) or not selectors.is_account_active(target):
        raise PermissionDenied("You can't follow this account.")
    actor_profile, target_profile = _profiles(actor, target)

    if actor_profile.following.filter(pk=target_profile.pk).exists():
        actor_profile.following.remove(target_profile)
        _withdraw(target, actor, Verb.FOLLOW)
        state = "none"
    elif FollowRequest.objects.filter(from_user=actor, to_user=target).exists():
        FollowRequest.objects.filter(from_user=actor, to_user=target).delete()
        _withdraw(target, actor, Verb.FOLLOW_REQUEST)
        state = "none"
    elif target_profile.is_private:
        FollowRequest.objects.create(from_user=actor, to_user=target)
        notify(target, actor, Verb.FOLLOW_REQUEST)
        state = "requested"
    else:
        actor_profile.following.add(target_profile)
        notify(target, actor, Verb.FOLLOW)
        state = "following"

    return {
        "state": state,
        "followers_count": target_profile.followers.count(),
    }


@transaction.atomic
def respond_to_follow_request(request_obj, user, accept):
    if request_obj.to_user_id != user.pk:
        raise PermissionDenied("This request isn't yours to answer.")
    requester = request_obj.from_user
    request_obj.delete()
    Notification.objects.filter(recipient=user, actor=requester, verb=Verb.FOLLOW_REQUEST).update(
        is_read=True
    )
    if accept and not selectors.is_blocked_between(user, requester):
        requester_profile, user_profile = _profiles(requester, user)
        requester_profile.following.add(user_profile)
        notify(requester, user, Verb.FOLLOW_ACCEPT)
        return True
    return False


@transaction.atomic
def set_private(user, is_private):
    profile = user.profile
    profile.is_private = is_private
    profile.save(update_fields=["is_private", "updated_at"])
    if not is_private:
        for request_obj in FollowRequest.objects.filter(to_user=user).select_related("from_user"):
            respond_to_follow_request(request_obj, user, accept=True)


def remove_follower(user, follower):
    user.profile.followers.remove(follower.profile)


# ---------------------------------------------------------------- blocking & reports


@transaction.atomic
def block_user(blocker, target):
    if blocker.pk == target.pk:
        raise ServiceError("You can't block yourself.")
    Block.objects.get_or_create(blocker=blocker, blocked=target)
    blocker_profile, target_profile = _profiles(blocker, target)
    blocker_profile.following.remove(target_profile)
    target_profile.following.remove(blocker_profile)
    FollowRequest.objects.filter(
        Q(from_user=blocker, to_user=target) | Q(from_user=target, to_user=blocker)
    ).delete()
    Notification.objects.filter(
        Q(recipient=blocker, actor=target) | Q(recipient=target, actor=blocker)
    ).delete()
    logger.info("event=user_blocked blocker=%s blocked=%s", blocker.pk, target.pk)


def unblock_user(blocker, target):
    Block.objects.filter(blocker=blocker, blocked=target).delete()


def create_report(reporter, reason, details="", post=None, comment=None, user=None):
    if reason not in Report.Reason.values:
        raise ValidationError("Choose a reason.", code="reason")
    if not any([post, comment, user]):
        raise ValidationError("Nothing to report.", code="target")
    reported_user = user or (post.user if post else comment.user)
    if reported_user.pk == reporter.pk:
        raise ServiceError("You can't report your own content.")
    details = clean_text(details, 1000, "Details", allow_empty=True)
    report = Report.objects.create(
        reporter=reporter,
        reason=reason,
        details=details,
        post=post,
        comment=comment,
        reported_user=reported_user,
    )
    logger.info("event=report_created report=%s reporter=%s", report.pk, reporter.pk)
    return report


# ---------------------------------------------------------------- messaging


def conversation_between(a, b):
    return (
        Conversation.objects.annotate(n=Count("participants"))
        .filter(n=2, participants=a)
        .filter(participants=b)
        .first()
    )


@transaction.atomic
def start_conversation(user, other):
    if other.pk == user.pk:
        raise ServiceError("You can't message yourself.")
    if selectors.is_blocked_between(user, other) or not selectors.is_account_active(other):
        raise PermissionDenied("You can't message this account.")
    existing = conversation_between(user, other)
    if existing:
        return existing, False
    conversation = Conversation.objects.create()
    conversation.participants.add(user, other)
    return conversation, True


def ensure_participant(conversation, user):
    if not conversation.participants.filter(pk=user.pk).exists():
        raise PermissionDenied("You're not part of this conversation.")


@transaction.atomic
def send_message(conversation, sender, content):
    ensure_participant(conversation, sender)
    text = clean_text(content, MESSAGE_MAX_LENGTH, "Message")
    participants = list(conversation.participants.all())
    others = [u for u in participants if u.pk != sender.pk]
    for other in others:
        if selectors.is_blocked_between(sender, other):
            raise PermissionDenied("You can't message this account.")

    message = Message.objects.create(conversation=conversation, sender=sender, content=text)
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message_at", "updated_at"])

    for other in others:
        existing = Notification.objects.filter(
            recipient=other, verb=Verb.MESSAGE, conversation=conversation, is_read=False
        )
        if existing.exists():
            existing.update(actor=sender, created_at=message.created_at)
        else:
            notify(other, sender, Verb.MESSAGE, conversation=conversation)

    payload = message.as_payload()
    payload["sender_name"] = sender.profile.name
    realtime.push_on_commit([u.pk for u in participants], {"type": "message", "message": payload})
    return message


@transaction.atomic
def mark_conversation_read(conversation, reader):
    ensure_participant(conversation, reader)
    unread = Message.objects.filter(conversation=conversation, is_read=False).exclude(sender=reader)
    last_id = unread.order_by("-pk").values_list("pk", flat=True).first()
    if last_id is None:
        return 0
    updated = unread.update(is_read=True, read_at=timezone.now())
    Notification.objects.filter(
        recipient=reader, verb=Verb.MESSAGE, conversation=conversation, is_read=False
    ).update(is_read=True)
    others = conversation.participants.exclude(pk=reader.pk).values_list("pk", flat=True)
    realtime.push_on_commit(
        list(others) + [reader.pk],
        {"type": "read", "conversation": conversation.pk, "reader_id": reader.pk, "up_to": last_id},
    )
    return updated


def unread_message_count(user):
    return Message.objects.filter(conversation__participants=user, is_read=False).exclude(sender=user).count()


# ---------------------------------------------------------------- accounts


@transaction.atomic
def deactivate_account(user):
    profile = user.profile
    profile.is_deactivated = True
    profile.deactivated_at = timezone.now()
    profile.save(update_fields=["is_deactivated", "deactivated_at", "updated_at"])
    logger.info("event=account_deactivated user=%s", user.pk)


def reactivate_account(user):
    profile = user.profile
    if profile.is_deactivated:
        profile.is_deactivated = False
        profile.deactivated_at = None
        profile.save(update_fields=["is_deactivated", "deactivated_at", "updated_at"])
        logger.info("event=account_reactivated user=%s", user.pk)
        return True
    return False


@transaction.atomic
def delete_account(user):
    user_id = user.pk
    # Deleting the User cascades to the profile, posts, comments, messages,
    # follows, blocks and notifications. Media files are removed by signals.
    User.objects.filter(pk=user_id).delete()
    logger.info("event=account_deleted user=%s", user_id)
