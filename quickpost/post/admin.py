from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone

from .models import (
    Block,
    Bookmark,
    Comment,
    Conversation,
    DailyQuote,
    FollowRequest,
    Hashtag,
    Message,
    Notification,
    Post,
    PostImage,
    Report,
    UserProfile,
)


def preview(text, length=50):
    return text if len(text) <= length else text[: length - 1] + "…"


class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 0
    fields = ("image", "width", "height", "alt_text", "position")
    readonly_fields = ("width", "height")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "content_preview", "created_at", "like_total", "comment_total")
    list_filter = ("created_at",)
    search_fields = ("content", "user__username")
    raw_id_fields = ("user", "repost_of", "likes", "dislikes", "mentions")
    inlines = [PostImageInline]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .annotate(_likes=Count("likes", distinct=True), _comments=Count("comments", distinct=True))
        )

    @admin.display(description="Content")
    def content_preview(self, obj):
        return preview(obj.content or "(repost)")

    @admin.display(description="Likes", ordering="_likes")
    def like_total(self, obj):
        return obj._likes

    @admin.display(description="Comments", ordering="_comments")
    def comment_total(self, obj):
        return obj._comments


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "post", "content_preview", "created_at", "is_reply")
    list_filter = ("created_at",)
    search_fields = ("content", "user__username")
    raw_id_fields = ("user", "post", "parent")

    @admin.display(description="Content")
    def content_preview(self, obj):
        return preview(obj.content, 40)

    @admin.display(boolean=True, description="Reply")
    def is_reply(self, obj):
        return obj.parent_id is not None


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "is_private", "email_verified", "is_deactivated", "created_at")
    list_filter = ("is_private", "email_verified", "is_deactivated")
    search_fields = ("user__username", "display_name", "bio")
    raw_id_fields = ("user", "following")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "reason", "status", "reported_user", "reporter", "target", "created_at")
    list_filter = ("status", "reason", "created_at")
    search_fields = ("details", "reported_user__username", "reporter__username")
    raw_id_fields = ("reporter", "post", "comment", "reported_user", "reviewed_by")
    readonly_fields = ("created_at", "reviewed_at", "reviewed_by")
    actions = ["dismiss", "remove_content", "deactivate_reported_user"]

    @admin.display(description="Target")
    def target(self, obj):
        if obj.comment_id:
            return f"Comment #{obj.comment_id}"
        if obj.post_id:
            return f"Post #{obj.post_id}"
        return "Account"

    def _close(self, request, queryset, status):
        return queryset.update(status=status, reviewed_by=request.user, reviewed_at=timezone.now())

    @admin.action(description="Dismiss selected reports")
    def dismiss(self, request, queryset):
        count = self._close(request, queryset, Report.Status.DISMISSED)
        self.message_user(request, f"Dismissed {count} report(s).")

    @admin.action(description="Remove reported post or comment")
    def remove_content(self, request, queryset):
        removed = 0
        for report in queryset.select_related("post", "comment"):
            if report.comment_id:
                report.comment.delete()
                removed += 1
            elif report.post_id:
                report.post.delete()
                removed += 1
        self._close(request, queryset, Report.Status.ACTIONED)
        self.message_user(request, f"Removed {removed} item(s).", messages.SUCCESS)

    @admin.action(description="Deactivate reported accounts")
    def deactivate_reported_user(self, request, queryset):
        users = {r.reported_user for r in queryset.select_related("reported_user") if r.reported_user}
        for user in users:
            user.is_active = False
            user.save(update_fields=["is_active"])
        self._close(request, queryset, Report.Status.ACTIONED)
        self.message_user(request, f"Deactivated {len(users)} account(s).", messages.WARNING)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "participants_list", "created_at", "last_message_at")
    raw_id_fields = ("participants",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("participants")

    @admin.display(description="Participants")
    def participants_list(self, obj):
        return ", ".join(u.username for u in obj.participants.all())


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "conversation", "content_preview", "created_at", "is_read")
    list_filter = ("created_at", "is_read")
    raw_id_fields = ("sender", "conversation")

    @admin.display(description="Content")
    def content_preview(self, obj):
        return preview(obj.content, 40)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "actor", "verb", "is_read", "created_at")
    list_filter = ("verb", "is_read")
    raw_id_fields = ("recipient", "actor", "post", "comment", "conversation")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    raw_id_fields = ("blocker", "blocked")


@admin.register(FollowRequest)
class FollowRequestAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "created_at")
    raw_id_fields = ("from_user", "to_user")


@admin.register(Hashtag)
class HashtagAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")
    raw_id_fields = ("user", "post")


@admin.register(DailyQuote)
class DailyQuoteAdmin(admin.ModelAdmin):
    list_display = ("text", "author", "source", "created_at")
