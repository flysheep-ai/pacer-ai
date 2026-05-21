"""Entry: python -m pacer.scheduler.runner"""
from __future__ import annotations
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.config import get_settings
from pacer.scheduler.jobs import morning_job, error_review_job, daily_report_job, goodnight_job, weekly_report_job


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sched = BlockingScheduler(timezone="Asia/Shanghai")

    def _wrap(fn):
        def _runner():
            sess = SessionLocal()
            try:
                fn(sess)
            finally:
                sess.close()
        return _runner

    sched.add_job(_wrap(morning_job), CronTrigger(hour=7, minute=0))
    sched.add_job(_wrap(error_review_job), CronTrigger(hour=18, minute=0))
    sched.add_job(_wrap(daily_report_job), CronTrigger(hour=21, minute=30))
    sched.add_job(_wrap(goodnight_job), CronTrigger(hour=22, minute=30))
    sched.add_job(_wrap(weekly_report_job), CronTrigger(day_of_week="sun", hour=21, minute=0))
    print("[scheduler] starting with 5 jobs (Asia/Shanghai)...")
    sched.start()


if __name__ == "__main__":
    main()
