import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def _scan_job(target_id: str) -> None:
    from app.scanner import run_scan_for_target
    log.info("Scheduled scan triggered for target %s", target_id)
    run_scan_for_target(target_id)


def register_job(target: dict) -> None:
    sched = get_scheduler()
    job_id = f"scan_{target['id']}"
    # Remove existing job if any
    if sched.get_job(job_id):
        sched.remove_job(job_id)
    schedule = (target.get("schedule") or "").strip()
    if not schedule:
        return
    try:
        # If it's a pure integer or float string → treat as interval in hours
        hours = float(schedule)
        trigger = IntervalTrigger(hours=hours)
        log.info("Registering interval job %s every %.1fh", job_id, hours)
    except ValueError:
        # Treat as cron expression (5 or 6 fields)
        trigger = CronTrigger.from_crontab(schedule, timezone="UTC")
        log.info("Registering cron job %s: %s", job_id, schedule)
    sched.add_job(_scan_job, trigger, id=job_id, args=[target["id"]],
                  replace_existing=True, misfire_grace_time=300)


def remove_job(target_id: str) -> None:
    sched = get_scheduler()
    job_id = f"scan_{target_id}"
    if sched.get_job(job_id):
        sched.remove_job(job_id)
        log.info("Removed scheduled job %s", job_id)


def reload_jobs(targets: list) -> None:
    for t in targets:
        if t.get("schedule"):
            register_job(t)


def start() -> None:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        log.info("APScheduler started")


def shutdown() -> None:
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        log.info("APScheduler stopped")
