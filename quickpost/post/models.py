from django.db import models
from django.contrib.auth.models import User
# Create your models here.
class Post(models.Model):
    # get the user who created the post
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=240)
    photo=models.ImageField(upload_to='photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    dislikes = models.ManyToManyField(User, related_name='disliked_posts', blank=True)

def __str__(self):
    # return the username and the content of the post
    # limiting the content to 20 characters for better readability
    return f"{self.user.username} - {self.content[:20]}"

