from django.db import migrations


def protect(apps, schema_editor):
    tables = [
        "audit_auditevent",
        "commitments_actionrecord",
        "commitments_workflowtransition",
        "commitments_occurrenceversion",
    ]
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE FUNCTION agenda_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Historical records are append-only'; END; $$"
        )
        for table in tables:
            schema_editor.execute(
                f"CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION agenda_append_only()"
            )
    elif schema_editor.connection.vendor == "sqlite":
        for table in tables:
            for operation in ["UPDATE", "DELETE"]:
                schema_editor.execute(
                    f"CREATE TRIGGER protect_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Historical records are append-only'); END"
                )


def unprotect(apps, schema_editor):
    tables = [
        "audit_auditevent",
        "commitments_actionrecord",
        "commitments_workflowtransition",
        "commitments_occurrenceversion",
    ]
    if schema_editor.connection.vendor == "postgresql":
        for table in tables:
            schema_editor.execute(f"DROP TRIGGER protect_history ON {table}")
        schema_editor.execute("DROP FUNCTION agenda_append_only()")
    elif schema_editor.connection.vendor == "sqlite":
        for table in tables:
            for operation in ["update", "delete"]:
                schema_editor.execute(f"DROP TRIGGER protect_{table}_{operation}")


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial"), ("commitments", "0002_counter")]
    operations = [migrations.RunPython(protect, unprotect)]
