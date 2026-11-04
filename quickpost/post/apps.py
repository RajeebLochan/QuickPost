from django.apps import AppConfig


class PostConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "post"
    verbose_name = "QuickPost"

    def ready(self):
        from . import signals  # noqa: F401  (registers signal handlers)
