"""Factory seams so tests can swap OCR / LLM without touching the pipeline."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from apps.llm.client import LLMClient, build_default_client

from .layout import LayoutDetector, YoloLayoutDetector
from .ocr import DocTROCR, FakeOCR, OCREngine


def get_ocr() -> OCREngine:
    if settings.OCR_ENGINE == "fake":
        return FakeOCR()
    return DocTROCR()


def get_llm() -> LLMClient:
    return build_default_client()


def get_layout() -> LayoutDetector | None:
    """Active retrained model if any, else the configured default weights, else None."""
    from apps.learning.models import ModelVersion  # lazy: learning depends on documents

    active = ModelVersion.objects.filter(is_active=True).first()
    path = active.path if active and Path(active.path).exists() else settings.LAYOUT_MODEL_PATH
    return YoloLayoutDetector(path) if path and Path(path).exists() else None
