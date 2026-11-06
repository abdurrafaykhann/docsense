"""Labelled evaluation sets: <dir>/manifest.jsonl + images/.

manifest line: {"id", "image": "images/x.png", "truth": {...}, "words": [...optional oracle OCR],
                "meta": {...}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Sample:
    id: str
    image_path: Path
    truth: dict
    words: list[dict] | None = None  # oracle OCR words (synthetic sets provide them)
    meta: dict = field(default_factory=dict)

    def load_image(self):
        from apps.pipeline.loader import load_pages

        data = self.image_path.read_bytes()
        ctype = "application/pdf" if self.image_path.suffix == ".pdf" else "image/png"
        return load_pages(data, ctype, max_pages=1)[0]


def load_set(directory: str | Path, limit: int | None = None) -> list[Sample]:
    directory = Path(directory)
    samples = []
    with (directory / "manifest.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            samples.append(
                Sample(
                    id=row["id"],
                    image_path=directory / row["image"],
                    truth=row["truth"],
                    words=row.get("words"),
                    meta=row.get("meta", {}),
                )
            )
            if limit and len(samples) >= limit:
                break
    return samples


def write_manifest(directory: str | Path, rows: list[dict]) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
