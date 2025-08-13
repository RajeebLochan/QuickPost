from django.urls import path
from . import views

urlpatterns = [
    path('', views.post_list, name='post_list'),
    path('create/', views.create_post, name='create_post'),
    path('edit/<int:post_id>/', views.edit_post, name='edit_post'),
    path('delete/<int:post_id>/', views.delete_post, name='delete_post'),
    path('index/', views.index, name='index'),
    path('register/', views.register, name='register'),  # This line is needed
    path('profile/', views.profile, name='profile'),  # Assuming you have a profile view   
    path('like/<int:post_id>/', views.like_post, name='like_post'),  # Assuming you have a like post view
    path('dislike/<int:post_id>/', views.dislike_post, name='dislike_post'),  # Assuming you have a dislike post view
]