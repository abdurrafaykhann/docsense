"""DocSense ML tooling. Reuses the Django-free pipeline from backend/ (apps.pipeline.core)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
