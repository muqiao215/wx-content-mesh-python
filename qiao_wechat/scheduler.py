from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from .db import db_session, init_db
from .models import Article, ArticleStatus
from .services.publisher import PublishService


scheduler = BackgroundScheduler(timezone="Asia/Singapore")


def schedule_freepublish(article_id: int, run_at: datetime) -> str:
    """Schedule freepublish submit for an existing draft/article.

    The process running this scheduler must stay alive. For production use, replace
    APScheduler with Celery/RQ + Redis or a durable cron worker.
    """
    init_db()

    def _job() -> None:
        with db_session() as db:
            PublishService(db).submit_freepublish(article_id)

    job = scheduler.add_job(_job, trigger="date", run_date=run_at, id=f"freepublish:{article_id}:{run_at.isoformat()}")
    if not scheduler.running:
        scheduler.start()
    return job.id


def schedule_poll(article_id: int, interval_seconds: int = 60) -> str:
    init_db()

    def _job() -> None:
        with db_session() as db:
            article = db.get(Article, article_id)
            if not article or article.status == ArticleStatus.published:
                return
            PublishService(db).poll_publish_status(article_id)

    job = scheduler.add_job(_job, trigger="interval", seconds=interval_seconds, id=f"poll:{article_id}", replace_existing=True)
    if not scheduler.running:
        scheduler.start()
    return job.id
