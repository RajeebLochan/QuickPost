from django.apps import AppConfig


class PostConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "post"

    def ready(self):
        # Start the scheduler when Django is ready
        # Prevent it from running during migrations or other management commands
        import sys
        
        # Don't start scheduler during migrations or certain commands
        if any(arg in sys.argv for arg in ['makemigrations', 'migrate', 'collectstatic', 'createsuperuser']):
            return
            
        # Only start scheduler in the main process (not worker processes)
        if 'runserver' in sys.argv:
            try:
                from . import scheduler
                scheduler.start_scheduler()
            except Exception as e:
                print(f"Error starting scheduler: {e}")
