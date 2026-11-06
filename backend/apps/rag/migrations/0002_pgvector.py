from django.db import migrations

from apps.rag import pgvector


def create_vector_table(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        pgvector.create_schema(schema_editor)


def drop_vector_table(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS rag_chunk_vec")


class Migration(migrations.Migration):
    dependencies = [("rag", "0001_initial")]
    operations = [migrations.RunPython(create_vector_table, drop_vector_table)]
