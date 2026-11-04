"""Read-side query helpers.

All visibility rules (deactivated accounts, blocks, private profiles) live
here so every list in the app applies them the same way, and every post
list is annotated with counts in a constant number of queries.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import (
    BooleanField,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Block, Bookmark, Comment, FollowRequest, Post, UserProfile

FollowThrough = UserProfile.following.through
LikeThrough = Post.likes.through
DislikeThrough = Post.dislikes.through


# ---------------------------------------------------------------- relations


def following_user_ids(user):
    """Subquery of user ids that `user` follows."""
    return FollowThrough.objects.filter(from_userprofile__user_id=user.pk).values("to_userprofile__user_id")


def follower_user_ids(user):
    return FollowThrough.objects.filter(to_userprofile__user_id=user.pk).values("from_userprofile__user_id")


def blocked_by_user_ids(user):
    return Block.objects.filter(blocker_id=user.pk).values("blocked_id")


def blockers_of_user_ids(user):
    return Block.objects.filter(blocked_id=user.pk).values("blocker_id")


def is_following(follower, target):
    if not follower.is_authenticated:
        return False
    return FollowThrough.objects.filter(
        from_userprofile__user_id=follower.pk, to_userprofile__user_id=target.pk
    ).exists()


def has_pending_request(follower, target):
    if not follower.is_authenticated:
        return False
    return FollowRequest.objects.filter(from_user_id=follower.pk, to_user_id=target.pk).exists()


def is_blocked_between(a, b):
    if not (a.is_authenticated and b.is_authenticated):
        return False
    return Block.objects.filter(
        Q(blocker_id=a.pk, blocked_id=b.pk) | Q(blocker_id=b.pk, blocked_id=a.pk)
    ).exists()


def has_blocked(blocker, target):
    if not blocker.is_authenticated:
        return False
    return Block.objects.filter(blocker_id=blocker.pk, blocked_id=target.pk).exists()


def is_account_active(user):
    return user.is_active and not user.profile.is_deactivated


def can_view_profile(viewer, owner):
    """Whether the profile page exists for this viewer at all."""
    if viewer.is_authenticated and viewer.pk == owner.pk:
        return True
    if not is_account_active(owner):
        return False
    return not is_blocked_between(viewer, owner)


def can_view_posts(viewer, owner):
    """Whether `viewer` may see `owner`'s posts (private accounts need approval)."""
    if not can_view_profile(viewer, owner):
        return False
    if viewer.is_authenticated and viewer.pk == owner.pk:
        return True
    if not owner.profile.is_private:
        return True
    return is_following(viewer, owner)


# ---------------------------------------------------------------- users


def active_users(viewer=None):
    qs = User.objects.filter(is_active=True, profile__is_deactivated=False)
    if viewer is not None and viewer.is_authenticated:
        qs = qs.exclude(pk__in=blocked_by_user_ids(viewer)).exclude(pk__in=blockers_of_user_ids(viewer))
    return qs.select_related("profile")


def with_follow_state(users_qs, viewer):
    """Annotate users with whether the viewer follows / has requested them."""
    if not viewer.is_authenticated:
        return users_qs.annotate(
            viewer_follows=Value(False, BooleanField()),
            viewer_requested=Value(False, BooleanField()),
        )
    return users_qs.annotate(
        viewer_follows=Exists(
            FollowThrough.objects.filter(
                from_userprofile__user_id=viewer.pk, to_userprofile__user_id=OuterRef("pk")
            )
        ),
        viewer_requested=Exists(
            FollowRequest.objects.filter(from_user_id=viewer.pk, to_user_id=OuterRef("pk"))
        ),
    )


def profile_stats(user):
    counts = UserProfile.objects.filter(pk=user.profile.pk).aggregate(
        followers=Count("followers", distinct=True),
        following=Count("following", distinct=True),
    )
    counts["posts"] = Post.objects.filter(user=user, repost_of__isnull=True).count()
    return counts


def suggested_users(viewer, limit=5):
    following = list(following_user_ids(viewer).values_list("to_userprofile__user_id", flat=True))
    requested = FollowRequest.objects.filter(from_user_id=viewer.pk).values("to_user_id")
    qs = (
        active_users(viewer)
        .exclude(pk=viewer.pk)
        .exclude(pk__in=following)
        .exclude(pk__in=requested)
        .annotate(
            mutual=Count(
                "profile__followers",
                filter=Q(profile__followers__user_id__in=following),
                distinct=True,
            ),
            follower_total=Count("profile__followers", distinct=True),
        )
        .order_by("-mutual", "-follower_total", "-date_joined")
    )
    return with_follow_state(qs, viewer)[:limit]


# ---------------------------------------------------------------- posts


def _author_visible_q(viewer, prefix=""):
    p = prefix
    q = Q(**{f"{p}user__is_active": True, f"{p}user__profile__is_deactivated": False})
    if viewer.is_authenticated:
        q &= ~Q(**{f"{p}user_id__in": blocked_by_user_ids(viewer)})
        q &= ~Q(**{f"{p}user_id__in": blockers_of_user_ids(viewer)})
        q &= (
            Q(**{f"{p}user__profile__is_private": False})
            | Q(**{f"{p}user_id": viewer.pk})
            | Q(**{f"{p}user_id__in": following_user_ids(viewer)})
        )
    else:
        q &= Q(**{f"{p}user__profile__is_private": False})
    return q


def visible_posts(viewer):
    """Posts the viewer is allowed to see, including the original of any repost."""
    return Post.objects.filter(
        _author_visible_q(viewer) & (Q(repost_of__isnull=True) | _author_visible_q(viewer, "repost_of__"))
    )


def _count(model, field="post"):
    sub = (
        model.objects.filter(**{field: OuterRef("pk")})
        .order_by()
        .values(field)
        .annotate(n=Count("pk"))
        .values("n")[:1]
    )
    return Coalesce(Subquery(sub, output_field=IntegerField()), 0)


def annotate_posts(qs, viewer):
    qs = (
        qs.select_related("user__profile")
        .prefetch_related("images")
        .annotate(
            likes_total=_count(LikeThrough),
            dislikes_total=_count(DislikeThrough),
            comments_total=_count(Comment),
            reposts_total=_count(Post, "repost_of"),
        )
    )
    if viewer.is_authenticated:
        qs = qs.annotate(
            viewer_liked=Exists(LikeThrough.objects.filter(post=OuterRef("pk"), user_id=viewer.pk)),
            viewer_disliked=Exists(DislikeThrough.objects.filter(post=OuterRef("pk"), user_id=viewer.pk)),
            viewer_saved=Exists(Bookmark.objects.filter(post=OuterRef("pk"), user_id=viewer.pk)),
            viewer_reposted=Exists(
                Post.objects.filter(repost_of=OuterRef("pk"), user_id=viewer.pk, content="")
            ),
        )
    else:
        false = Value(False, BooleanField())
        qs = qs.annotate(viewer_liked=false, viewer_disliked=false, viewer_saved=false, viewer_reposted=false)
    return qs


def hydrate(posts, viewer):
    """Attach `display` (what to render) and `embedded` (quoted original) to each post.

    Originals of reposts are fetched in one extra query, already annotated.
    """
    posts = list(posts)
    original_ids = {p.repost_of_id for p in posts if p.repost_of_id}
    originals = {}
    if original_ids:
        originals = {o.pk: o for o in annotate_posts(Post.objects.filter(pk__in=original_ids), viewer)}
    for p in posts:
        original = originals.get(p.repost_of_id)
        p.display = original if (p.is_plain_repost and original) else p
        p.embedded = original if (p.repost_of_id and not p.is_plain_repost) else None
    return posts


def following_feed(viewer):
    return (
        visible_posts(viewer)
        .filter(Q(user_id=viewer.pk) | Q(user_id__in=following_user_ids(viewer)))
        .order_by("-created_at")
    )


def explore_posts(viewer, days=14):
    since = timezone.now() - timedelta(days=days)
    return (
        annotate_posts(visible_posts(viewer).filter(repost_of__isnull=True, created_at__gte=since), viewer)
        .annotate(score=F("likes_total") + 2 * F("comments_total") + 3 * F("reposts_total"))
        .order_by("-score", "-created_at")
    )


def trending_hashtags(viewer, days=7, limit=8):
    since = timezone.now() - timedelta(days=days)
    from .models import Hashtag

    visible_ids = visible_posts(viewer).filter(created_at__gte=since).values("pk")
    return (
        Hashtag.objects.filter(posts__in=visible_ids)
        .annotate(uses=Count("posts", distinct=True))
        .order_by("-uses", "name")[:limit]
    )


# ---------------------------------------------------------------- pagination


@dataclass
class Page:
    items: list
    number: int
    has_next: bool

    @property
    def next_number(self):
        return self.number + 1


def paginate(request, qs, per_page=20, param="page"):
    """Offset pagination without a COUNT query: fetch one extra row to detect a next page."""
    try:
        number = max(1, int(request.GET.get(param, 1)))
    except (TypeError, ValueError):
        number = 1
    number = min(number, 500)
    start = (number - 1) * per_page
    rows = list(qs[start : start + per_page + 1])
    return Page(items=rows[:per_page], number=number, has_next=len(rows) > per_page)
