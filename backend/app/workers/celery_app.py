"""Celery application: async task execution + scheduled jobs."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "tradebot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # redeliver on worker crash — no lost jobs
    worker_prefetch_multiplier=1,
)

celery.autodiscover_tasks(["app.workers.tasks"])

# Schedules carry no holiday logic — tasks consult the Market Calendar and no-op
# on non-trading days (spec §3: no scheduler relies on hardcoded dates).
celery.conf.beat_schedule = {
    # Refresh the instrument universe and trading calendar before the day's sync,
    # so ingestion runs against a current master and an accurate holiday list.
    "sync-universe": {
        "task": "market_data.sync_universe",
        "schedule": crontab(hour=7, minute=0),       # 07:00 IST, pre-open
    },
    "sync-calendar": {
        "task": "market_data.sync_calendar",
        "schedule": crontab(hour=7, minute=30, day_of_week="sun"),
    },
    "sync-eod-nse": {
        "task": "market_data.sync_eod",
        "schedule": crontab(hour=18, minute=0),      # 18:00 IST, after close
        "kwargs": {"exchange": "NSE", "timeframe": "1d"},
    },
    "sync-corporate-actions": {
        "task": "market_data.sync_corporate_actions",
        "schedule": crontab(hour=20, minute=0, day_of_week="sun"),
        "kwargs": {"exchange": "NSE"},
    },
    "provider-health-probe": {
        "task": "market_data.provider_health_probe",
        "schedule": crontab(minute="*/15"),
    },
}
