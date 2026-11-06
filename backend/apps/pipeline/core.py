"""Django-free pipeline core: images -> OCR -> LLM -> validation -> scores.

Used by the Celery runner (which adds DB persistence + progress) and by the offline
evaluation harness in ml/ (which adds datasets + metrics).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from apps.validation import rules, scoring
from apps.validation.grounding import Word
from apps.validation.schema import InvoiceExtraction

from . import extract as extract_mod
from .cleanup import clean_image
from .grouping import pages_to_prompt_text, pages_to_region_prompt_text, regions_usable
from .layout import LayoutDetector, Region

StepHook = Callable[[str, str, str], None]  # (step, status, detail)
TextBuilder = Callable[[dict[int, list[Word]], int], str]


def whole_page_text(words_by_page: dict[int, list[Word]], max_chars: int) -> str:
    """Arm A: reading-order text of the entire page(s)."""
    return pages_to_prompt_text(words_by_page, max_chars)


@dataclass
class PipelineResult:
    invoice: InvoiceExtraction
    issues: list[rules.Issue]
    scores: list[scoring.FieldScore]
    overall: float
    needs_review: bool
    words_by_page: dict[int, list[Word]]
    cleaned: list[np.ndarray] = field(default_factory=list)
    prompt_text: str = ""
    cleanup_notes: list[float] = field(default_factory=list)
    regions_by_page: dict[int, list[Region]] = field(default_factory=dict)
    layout_used: bool = False

    @property
    def all_words(self) -> list[Word]:
        return [w for p in sorted(self.words_by_page) for w in self.words_by_page[p]]


def _noop(step: str, status: str, detail: str = "") -> None:
    return None


def process(
    images: list[np.ndarray],
    ocr,
    llm,
    *,
    max_chars: int = 12000,
    clean: bool = True,
    text_builder: TextBuilder = whole_page_text,
    default_tax_rate: float = rules.DEFAULT_TAX_RATE,
    today: date | None = None,
    on_step: StepHook = _noop,
    words_by_page: dict[int, list[Word]] | None = None,
    layout: LayoutDetector | None = None,
    regions_by_page: dict[int, list[Region]] | None = None,
) -> PipelineResult:
    """Run cleanup -> OCR -> extract -> validate -> score.

    `words_by_page` lets callers supply cached OCR (skips cleanup + OCR).
    """
    cleaned: list[np.ndarray] = []
    notes: list[float] = []
    if words_by_page is None:
        on_step("cleanup", "running", "")
        for img in images:
            if clean:
                out, info = clean_image(img)
                notes.append(info["deskew_deg"])
            else:
                out = img
            cleaned.append(out)
        on_step("cleanup", "done", f"deskew {notes}°")

        on_step("ocr", "running", "")
        words_by_page = {i + 1: ocr.read(img, page=i + 1) for i, img in enumerate(cleaned)}
        n_words = sum(len(w) for w in words_by_page.values())
        on_step("ocr", "done", f"{n_words} words")
    else:
        cleaned = images

    # layout: detect regions on the cleaned page images (or accept supplied/oracle regions)
    if regions_by_page is None and layout is not None:
        on_step("layout", "running", "")
        regions_by_page = {i + 1: layout.detect(img, page=i + 1) for i, img in enumerate(cleaned)}
        found = sum(len(r) for r in regions_by_page.values())
        usable = all(regions_usable(r) for r in regions_by_page.values())
        on_step(
            "layout", "done", f"{found} regions" + ("" if usable else " (fallback: whole page)")
        )
    elif regions_by_page is None:
        on_step("layout", "skipped", "no layout model")
    regions_by_page = regions_by_page or {}
    layout_used = any(regions_usable(r) for r in regions_by_page.values())

    on_step("extract", "running", "")
    if layout_used and text_builder is whole_page_text:
        text = pages_to_region_prompt_text(words_by_page, regions_by_page, max_chars)
    else:
        text = text_builder(words_by_page, max_chars)
    inv = extract_mod.extract(llm, text)
    on_step("extract", "done", "")

    on_step("validate", "running", "")
    all_words = [w for p in sorted(words_by_page) for w in words_by_page[p]]
    issues = rules.validate(inv, today=today, default_rate=default_tax_rate)
    scores = scoring.score_fields(inv, issues, all_words)
    overall = scoring.overall_confidence(scores)
    review = scoring.needs_review(scores, issues)
    on_step("validate", "done", f"{len(issues)} issue(s)")
    return PipelineResult(
        inv,
        issues,
        scores,
        overall,
        review,
        words_by_page,
        cleaned,
        text,
        notes,
        regions_by_page,
        layout_used,
    )
