from pathlib import Path

from django.core.management.base import BaseCommand

from apps.learning.services import export_feedback


class Command(BaseCommand):
    help = "Export approved documents as a YOLO layout dataset + extraction manifest."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="ml/data/feedback")
        parser.add_argument("--workspace", type=int)

    def handle(self, *args, **opts):
        n = export_feedback(Path(opts["out"]), opts["workspace"])
        self.stdout.write(f"exported {n} samples to {opts['out']}")
