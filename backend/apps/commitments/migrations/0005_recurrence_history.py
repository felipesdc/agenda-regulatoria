from django.db import migrations


def protect(apps, schema_editor):
    table = "commitments_recurrenceversion"
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION agenda_append_only()"
        )
    elif schema_editor.connection.vendor == "sqlite":
        for op in ["UPDATE", "DELETE"]:
            schema_editor.execute(
                f"CREATE TRIGGER protect_{table}_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'Historical records are append-only'); END"
            )


def unprotect(apps, schema_editor):
    table = "commitments_recurrenceversion"
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f"DROP TRIGGER protect_history ON {table}")
    elif schema_editor.connection.vendor == "sqlite":
        for op in ["update", "delete"]:
            schema_editor.execute(f"DROP TRIGGER protect_{table}_{op}")


class Migration(migrations.Migration):
    dependencies = [
        ("commitments", "0004_holiday_commitmentoccurrence_periodicity_and_more"),
        ("audit", "0002_append_only"),
    ]
    operations = [migrations.RunPython(protect, unprotect)]
