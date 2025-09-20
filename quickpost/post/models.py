from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from PIL import Image

# Create your models here.
class Post(models.Model):
    # get the user who created the post
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=240)
    photo = models.ImageField(upload_to='photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    dislikes = models.ManyToManyField(User, related_name='disliked_posts', blank=True)

    class Meta:
        ordering = ['-created_at']  # Default ordering by newest first

    def __str__(self):
        # return the username and the content of the post
        # limiting the content to 20 characters for better readability
        return f"{self.user.username} - {self.content[:20]}"

    def clean(self):
        """Validate post data"""
        if not self.content.strip():
            raise ValidationError('Post content cannot be empty.')
        if len(self.content) > 240:
            raise ValidationError('Post content cannot exceed 240 characters.')

    def get_likes_count(self):
        """Get total number of likes"""
        return self.likes.count()

    def get_dislikes_count(self):
        """Get total number of dislikes"""
        return self.dislikes.count()

    def get_comments_count(self):
        """Get total number of comments"""
        return self.comments.count()

    def is_liked_by(self, user):
        """Check if user has liked this post"""
        return self.likes.filter(id=user.id).exists()

    def is_disliked_by(self, user):
        """Check if user has disliked this post"""
        return self.dislikes.filter(id=user.id).exists()

    def toggle_like(self, user):
        """Toggle like status for a user"""
        if self.is_liked_by(user):
            self.likes.remove(user)
            return False
        else:
            self.likes.add(user)
            self.dislikes.remove(user)  # Remove dislike if exists
            return True

    def toggle_dislike(self, user):
        """Toggle dislike status for a user"""
        if self.is_disliked_by(user):
            self.dislikes.remove(user)
            return False
        else:
            self.dislikes.add(user)
            self.likes.remove(user)  # Remove like if exists
            return True

    @property
    def engagement_score(self):
        """Calculate engagement based on likes, dislikes, and comments"""
        return self.get_likes_count() + self.get_comments_count() - self.get_dislikes_count()

    @property
    def time_since_created(self):
        """Get time elapsed since post creation"""
        return timezone.now() - self.created_at

    @property
    def net_likes(self):
        """Get net likes (likes - dislikes)"""
        return self.get_likes_count() - self.get_dislikes_count()


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=500)  # Added max length
    created_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)  # For replies

    class Meta:
        ordering = ['created_at']  # Order comments by oldest first

    def __str__(self):
        return f"{self.user.username}: {self.content[:20]}"
 
    def clean(self):
        """Validate comment data"""
        if not self.content.strip():
            raise ValidationError('Comment content cannot be empty.')
        if len(self.content) > 500:
            raise ValidationError('Comment content cannot exceed 500 characters.')

    def is_reply(self):
        """Check if this comment is a reply to another comment"""
        return self.parent is not None

    def get_replies(self):
        """Get all replies to this comment"""
        return Comment.objects.filter(parent=self)

    def get_replies_count(self):
        """Get total number of replies"""
        return self.get_replies().count()

    @property
    def time_since_created(self):
        """Get time elapsed since comment creation"""
        return timezone.now() - self.created_at
    


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, help_text="Tell us about yourself")
    profile_image = models.ImageField(upload_to='profile_pics/', default='profile_pics/default.jpg', blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=200, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Follow system
    following = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='followers', 
        blank=True,
        help_text="Users that this user is following"
    )

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Resize image if it's too large
        if self.profile_image:
            img = Image.open(self.profile_image.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.profile_image.path)

    @property
    def get_posts_count(self):
        return self.user.post_set.count()

    @property
    def get_followers_count(self):
        """Get the number of followers"""
        return self.followers.count()

    @property
    def get_following_count(self):
        """Get the number of users this user is following"""
        return self.following.count()

    def is_following(self, user_profile):
        """Check if this user is following another user"""
        return self.following.filter(id=user_profile.id).exists()

    def follow(self, user_profile):
        """Follow another user"""
        if not self.is_following(user_profile) and self != user_profile:
            self.following.add(user_profile)
            return True
        return False

    def unfollow(self, user_profile):
        """Unfollow another user"""
        if self.is_following(user_profile):
            self.following.remove(user_profile)
            return True
        return False

    def toggle_follow(self, user_profile):
        """Toggle follow status for another user"""
        if self.is_following(user_profile):
            self.unfollow(user_profile)
            return False  # Now unfollowing
        else:
            self.follow(user_profile)
            return True   # Now following

# Signal to create profile automatically when user is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)


class Conversation(models.Model):
    """Model to represent a conversation between two users"""
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        participants_list = list(self.participants.all())
        if len(participants_list) >= 2:
            return f"Conversation between {participants_list[0].username} and {participants_list[1].username}"
        return f"Conversation {self.id}"
    
    @property
    def last_message(self):
        """Get the last message in this conversation"""
        return self.messages.order_by('-created_at').first()
    
    def get_other_participant(self, user):
        """Get the other participant in a two-person conversation"""
        return self.participants.exclude(id=user.id).first()
    
    def has_unread_messages(self, user):
        """Check if the conversation has unread messages for the user"""
        return self.messages.filter(is_read=False).exclude(sender=user).exists()


class Message(models.Model):
    """Model to represent individual messages in conversations"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Message from {self.sender.username}: {self.content[:30]}"
    
    def clean(self):
        """Validate message data"""
        if not self.content.strip():
            raise ValidationError('Message content cannot be empty.')
        if len(self.content) > 1000:
            raise ValidationError('Message content cannot exceed 1000 characters.')
    
    @property
    def time_since_created(self):
        """Get time elapsed since message creation"""
        return timezone.now() - self.created_at
    
    def mark_as_read(self):
        """Mark this message as read"""
        self.is_read = True
        self.save()
