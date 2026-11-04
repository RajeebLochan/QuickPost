from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = "QuickPost moderation"
admin.site.site_title = "QuickPost admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("post.urls")),
]

if settings.SERVE_MEDIA:
    # Development only. In production the web server or object storage serves uploads.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
