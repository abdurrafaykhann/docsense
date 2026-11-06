from celery import shared_task

from .runner import run_pipeline


@shared_task(name="pipeline.process_document")
def process_document(document_id: int) -> int:
    run_pipeline(document_id)
    return document_id
