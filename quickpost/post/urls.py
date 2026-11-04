from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from .views import accounts, discovery, messaging, notifications, pages, posts, profiles

urlpatterns = [
    path("", pages.home, name="home"),
    path("feed/", pages.feed, name="feed"),
    path("explore/", pages.explore, name="explore"),
    path("search/", discovery.search, name="search"),
    path("tags/<str:name>/", discovery.hashtag, name="hashtag"),
    path("saved/", discovery.saved, name="saved"),
    # Posts
    path("compose/", posts.compose, name="compose"),
    path("p/<int:pk>/", posts.post_detail, name="post_detail"),
    path("p/<int:pk>/edit/", posts.post_edit, name="post_edit"),
    path("p/<int:pk>/delete/", posts.post_delete, name="post_delete"),
    path("p/<int:pk>/react/<str:kind>/", posts.react, name="post_react"),
    path("p/<int:pk>/repost/", posts.repost, name="post_repost"),
    path("p/<int:pk>/save/", posts.bookmark, name="post_save"),
    path("p/<int:pk>/comments/", posts.comments_list, name="comments_list"),
    path("p/<int:pk>/comments/new/", posts.comment_create, name="comment_create"),
    path("comments/<int:pk>/delete/", posts.comment_delete, name="comment_delete"),
    # People
    path("u/<str:username>/", profiles.profile, name="profile"),
    path("u/<str:username>/followers/", profiles.followers, name="followers"),
    path("u/<str:username>/following/", profiles.following, name="following"),
    path("u/<str:username>/follow/", profiles.toggle_follow, name="toggle_follow"),
    path("u/<str:username>/block/", profiles.toggle_block, name="toggle_block"),
    path("u/<str:username>/message/", profiles.message_user, name="message_user"),
    path("follow-requests/", profiles.follow_requests, name="follow_requests"),
    path(
        "follow-requests/<int:pk>/<str:decision>/",
        profiles.respond_follow_request,
        name="respond_follow_request",
    ),
    path("report/", profiles.report, name="report"),
    # Notifications
    path("notifications/", notifications.notifications, name="notifications"),
    path("notifications/menu/", notifications.notifications_dropdown, name="notifications_dropdown"),
    path("notifications/<int:pk>/open/", notifications.open_notification, name="open_notification"),
    path("notifications/read-all/", notifications.mark_all_read, name="notifications_read_all"),
    # Messages
    path("messages/", messaging.inbox, name="inbox"),
    path("messages/<int:pk>/", messaging.chat_room, name="chat_room"),
    path("messages/<int:pk>/history/", messaging.history, name="chat_history"),
    path("messages/<int:pk>/send/", messaging.send, name="chat_send"),
    path("messages/<int:pk>/read/", messaging.mark_read, name="chat_read"),
    # Accounts
    path("accounts/login/", accounts.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", accounts.register, name="register"),
    path("accounts/verify/resend/", accounts.resend_verification, name="resend_verification"),
    path("accounts/verify/<str:token>/", accounts.verify_email, name="verify_email"),
    path("accounts/password/reset/", accounts.PasswordResetView.as_view(), name="password_reset"),
    path("accounts/password/reset/sent/", accounts.password_reset_done, name="password_reset_done"),
    path(
        "accounts/password/reset/<uidb64>/<token>/",
        accounts.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("accounts/password/reset/done/", accounts.password_reset_complete, name="password_reset_complete"),
    path("welcome/", accounts.onboarding, name="onboarding"),
    # Settings
    path("settings/", RedirectView.as_view(pattern_name="settings_profile"), name="settings"),
    path("settings/profile/", accounts.settings_profile, name="settings_profile"),
    path("settings/account/", accounts.settings_account, name="settings_account"),
    path("settings/privacy/", accounts.settings_privacy, name="settings_privacy"),
    path("settings/password/", accounts.settings_password, name="settings_password"),
    path("settings/deactivate/", accounts.deactivate, name="deactivate_account"),
    path("settings/delete/", accounts.delete_account, name="delete_account"),
    # Old addresses from the first version of QuickPost
    path("post/", RedirectView.as_view(pattern_name="feed", permanent=True)),
    path("post/profile/<str:username>/", RedirectView.as_view(pattern_name="profile", permanent=True)),
    path("post/conversations/", RedirectView.as_view(pattern_name="inbox", permanent=True)),
    path("post/register/", RedirectView.as_view(pattern_name="register", permanent=True)),
]
