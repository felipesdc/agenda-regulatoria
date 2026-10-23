from django.db import migrations


def protect(apps, schema_editor):
    table = "customfields_formversion"
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION agenda_append_only()"
        )
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ["UPDATE", "DELETE"]:
            schema_editor.execute(
                f"CREATE TRIGGER protect_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Historical records are append-only'); END"
            )


def unprotect(apps, schema_editor):
    table = "customfields_formversion"
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f"DROP TRIGGER protect_history ON {table}")
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ["update", "delete"]:
            schema_editor.execute(f"DROP TRIGGER protect_{table}_{operation}")


class Migration(migrations.Migration):
    dependencies = [
        ("customfields", "0001_initial"),
        ("audit", "0002_append_only"),
        ("commitments", "0008_commitmentdefinition_form_version_and_more"),
    ]
    operations = [migrations.RunPython(protect, unprotect)]
