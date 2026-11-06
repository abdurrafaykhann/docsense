from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.evaluation.importer import import_file


class Command(BaseCommand):
    help = "Import evaluation result JSON files (default: docs/eval-results/*.json)."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*")

    def handle(self, *args, **opts):
        files = [Path(p) for p in opts["paths"]] or sorted(
            (settings.BASE_DIR.parent / "docs" / "eval-results").glob("*.json")
        )
        for f in files:
            run, created = import_file(f)
            self.stdout.write(f"{'created' if created else 'updated'} {run.kind} {f.name}")
