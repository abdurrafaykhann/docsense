"""Factory seams so tests can swap OCR / LLM without touching the pipeline."""

from __future__ import annotations

from django.conf import settings

from apps.llm.client import LLMClient, build_default_client

from .ocr import DocTROCR, FakeOCR, OCREngine


def get_ocr() -> OCREngine:
    if settings.OCR_ENGINE == "fake":
        return FakeOCR()
    return DocTROCR()


def get_llm() -> LLMClient:
    return build_default_client()
