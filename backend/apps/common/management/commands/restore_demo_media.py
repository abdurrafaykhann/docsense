"""Re-create the demo's image files on an ephemeral disk (free hosts wipe it on every restart).

The database keeps the rows; the 50 sample images ship inside the image under SEED_DIR.
Files are matched by SHA-256, so nothing depends on how Django named them. Idempotent.
"""

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.documents.models import Document


class Command(BaseCommand):
    help = "Write missing demo document/page images from the bundled seed pack."

    def handle(self, *args, **opts):
        pack = Path(settings.SEED_DIR)
        manifest = pack / "manifest.json"
        if not manifest.exists():
            self.stdout.write("no seed pack; nothing to restore")
            return
        by_sha = {}
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            raw = (pack / row["file"]).read_bytes()
            by_sha[hashlib.sha256(raw).hexdigest()] = raw
        restored = 0
        for doc in Document.objects.filter(workspace__is_demo=True):
            raw = by_sha.get(doc.sha256)
            if raw is None:
                continue
            for field in [doc.file] + [p.image for p in doc.pages.all()]:
                if field and not Path(field.path).exists():
                    path = Path(field.path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    restored += 1
        self.stdout.write(f"restored {restored} demo image files")
