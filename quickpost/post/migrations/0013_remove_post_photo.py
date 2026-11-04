from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("post", "0012_preserve_existing_data")]

    operations = [migrations.RemoveField(model_name="post", name="photo")]
