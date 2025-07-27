from . import views
from django.urls import path

urlpatterns = [
    path("", views.post_list, name="post_list"),
    path("create/", views.create_post, name="create_post"),
    path("edit/<int:post_id>/", views.edit_post, name="edit_post"),
    path("delete/<int:post_id>/", views.delete_post, name="delete_post"),
    path("index/", views.index, name="index"),
    # Uncomment the following line to require login for all views   
] 