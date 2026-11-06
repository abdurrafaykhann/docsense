from celery import shared_task


@shared_task(name="learning.retrain")
def retrain_task(job_id: int) -> int:
    from .models import RetrainJob
    from .services import run_retrain

    job = RetrainJob.objects.get(pk=job_id)
    try:
        run_retrain(job)
    except Exception:  # noqa: BLE001 - failure is recorded on the job
        pass
    return job_id
