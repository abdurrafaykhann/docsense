from django.core.management.base import BaseCommand, CommandError

from apps.learning import services
from apps.learning.models import ModelVersion


class Command(BaseCommand):
    help = "Activate a registered layout model by name, or --rollback to its parent."

    def add_arguments(self, parser):
        parser.add_argument("name", nargs="?")
        parser.add_argument("--rollback", action="store_true")

    def handle(self, *args, **opts):
        if opts["rollback"]:
            restored = services.rollback()
            self.stdout.write(f"active: {restored.name if restored else 'default weights'}")
            return
        try:
            v = ModelVersion.objects.get(name=opts["name"])
        except ModelVersion.DoesNotExist as exc:
            raise CommandError(f"no model named {opts['name']}") from exc
        services.activate(v)
        self.stdout.write(f"activated {v.name}")
