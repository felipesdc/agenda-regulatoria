from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model("commitments", "IdentifierCounter").objects.get_or_create(name="commitment")


class Migration(migrations.Migration):
    dependencies = [("commitments", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
