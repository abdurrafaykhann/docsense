from django.core.management.base import BaseCommand, CommandError

from apps.learning import services


class Command(BaseCommand):
    help = "Fine-tune the layout model on approved documents and compare it with the current one."

    def add_arguments(self, parser):
        parser.add_argument("--epochs", type=int, default=5)
        parser.add_argument("--activate", action="store_true", help="activate if it is safe")

    def handle(self, *args, **opts):
        try:
            version = services.run_retrain(epochs=opts["epochs"])
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc
        m = version.metrics
        self.stdout.write(f"trained {version.name} on {version.n_feedback} approved documents")
        for name, delta in m["deltas"].items():
            self.stdout.write(
                f"  {name:18s} map50 {m['previous'][name]['map50']:.3f} -> "
                f"{m['new'][name]['map50']:.3f} ({delta:+.3f})"
            )
        verdict = "SAFE to activate" if m["recommend_activate"] else "NOT recommended"
        self.stdout.write(verdict)
        if opts["activate"] and m["recommend_activate"]:
            services.activate(version)
            self.stdout.write(f"activated {version.name}")
