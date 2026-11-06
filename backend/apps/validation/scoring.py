"""Per-field confidence and review routing. Weights are config, calibrated later (M4/M14)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .grounding import Location, Word, locate
from .rules import Issue
from .schema import REQUIRED_FIELDS, SCALAR_FIELDS, InvoiceExtraction

REVIEW_THRESHOLD = 0.70
NOT_IN_OCR_PENALTY = 0.6
ERROR_PENALTY = 0.5
WARN_PENALTY = 0.8
UNGROUNDED_OK = {"currency", "tax_rate"}  # often implied, not printed verbatim


@dataclass
class FieldScore:
    name: str
    value: object
    confidence: float
    flags: list[str] = field(default_factory=list)
    location: Location | None = None


def score_fields(
    inv: InvoiceExtraction, issues: list[Issue], words: list[Word]
) -> list[FieldScore]:
    out: list[FieldScore] = []
    for name in [*SCALAR_FIELDS, "line_items"]:
        value = getattr(inv, name)
        loc = None
        flags: list[str] = []

        if name == "line_items":
            present = bool(value)
            conf = 1.0 if present else 0.0
            if not present:
                flags.append("missing")
        elif value in (None, ""):
            conf, present = 0.0, False
            flags.append("missing")
        else:
            present = True
            loc = locate(name, value, words)
            if loc:
                conf = max(0.0, min(1.0, loc.conf * (0.5 + 0.5 * loc.match)))
            elif name in UNGROUNDED_OK:
                conf = 0.9
            else:
                conf = NOT_IN_OCR_PENALTY
                flags.append("not_in_ocr")

        if present:
            for issue in issues:
                if name in issue.fields:
                    conf *= ERROR_PENALTY if issue.severity == "error" else WARN_PENALTY
                    flags.append(issue.code)
        out.append(FieldScore(name, value, round(conf, 4), flags, loc))
    return out


def overall_confidence(scores: list[FieldScore]) -> float:
    present = [s for s in scores if s.confidence > 0 and s.name != "currency"]
    required = [s.confidence for s in scores if s.name in REQUIRED_FIELDS]
    if not present or not required:
        return 0.0
    return round(0.5 * min(required) + 0.5 * sum(s.confidence for s in present) / len(present), 4)


def needs_review(scores: list[FieldScore], issues: list[Issue]) -> bool:
    if any(i.severity == "error" for i in issues):
        return True
    return any(
        s.confidence < REVIEW_THRESHOLD for s in scores if s.name != "line_items" and s.value
    ) or any(s.name in REQUIRED_FIELDS and not s.value for s in scores)
