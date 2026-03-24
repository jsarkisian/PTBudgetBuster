"""Engagement scheduler.

On startup, loads all engagements with status='scheduled' and registers
APScheduler jobs to start them at their scheduled_at time.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime


scheduler = AsyncIOScheduler()


async def schedule_engagement(db, engagement_id: str, run_fn):
    """Register a scheduled engagement with APScheduler.

    Args:
        db: Database instance
        engagement_id: The engagement to schedule
        run_fn: Async function to call with engagement_id to start the run
    """
    eng = await db.get_engagement(engagement_id)
    if not eng or not eng.get("scheduled_at"):
        return
    trigger = DateTrigger(run_date=datetime.fromisoformat(eng["scheduled_at"]))
    scheduler.add_job(run_fn, trigger, args=[engagement_id], id=engagement_id, replace_existing=True)


async def restore_schedules(db, run_fn):
    """On startup, re-register all scheduled engagements."""
    engagements = await db.list_engagements()
    for eng in engagements:
        if eng["status"] == "scheduled" and eng.get("scheduled_at"):
            await schedule_engagement(db, eng["id"], run_fn)


def cancel_schedule(engagement_id: str):
    """Cancel a scheduled engagement."""
    try:
        scheduler.remove_job(engagement_id)
    except Exception:
        pass
