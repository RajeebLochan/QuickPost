from django.contrib import admin
from .models import Post, Comment, UserProfile, Conversation, Message

# Register your models here.

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_preview', 'created_at', 'get_likes_count', 'get_comments_count')
    list_filter = ('created_at', 'user')
    search_fields = ('content', 'user__username')
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'content_preview', 'created_at', 'is_reply')
    list_filter = ('created_at', 'post')
    search_fields = ('content', 'user__username')
    
    def content_preview(self, obj):
        return obj.content[:30] + '...' if len(obj.content) > 30 else obj.content
    content_preview.short_description = 'Content'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bio_preview', 'get_followers_count', 'get_following_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'bio')
    
    def bio_preview(self, obj):
        return obj.bio[:30] + '...' if len(obj.bio) > 30 else obj.bio
    bio_preview.short_description = 'Bio'

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'participants_list', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    
    def participants_list(self, obj):
        return ', '.join([user.username for user in obj.participants.all()])
    participants_list.short_description = 'Participants'

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'conversation', 'content_preview', 'created_at', 'is_read')
    list_filter = ('created_at', 'is_read')
    search_fields = ('content', 'sender__username')
    
    def content_preview(self, obj):
        return obj.content[:40] + '...' if len(obj.content) > 40 else obj.content
    content_preview.short_description = 'Content'