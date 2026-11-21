"""Background jobs (S5): run every minute by a background thread, or on demand from the admin console."""
import logging
import threading
import time

from . import notifications as notify
from .db import Database
from .plan_service import check_unmarked
from .progress import store_weekly_summary
from .security import log_event
from .timeutil import now

log = logging.getLogger("jobs")


def run_all(db, current):
    result = {
        "missed_sessions_rescheduled": check_unmarked(db, current),   # FR-18
        "deadline_alerts_created": notify.create_deadline_alerts(db, current),  # FR-22
    }
    # Sunday from 18:00 (FR-24). The whole hour is used so a run is never skipped; saving twice only updates the row.
    if current.weekday() == 6 and current.hour == 18:
        for s in db.query("SELECT user_id FROM students"):
            store_weekly_summary(db, s["user_id"], current)
    result["notifications_sent"] = notify.deliver_due(db, current)  # FR-21, NFR-04
    return result


def start_background_jobs(app):
    """Simple timer thread. Runs only once per process; disable with ENABLE_JOBS=0."""
    def loop():
        while True:
            time.sleep(app.config["JOB_INTERVAL_SECONDS"])
            db = None
            try:
                db = Database(app.config["DATABASE_URL"])
                run_all(db, now())
                db.commit()
            except Exception as exc:  # keep the thread alive; record the problem for the admin log
                log.exception("Background job failed")
                try:
                    if db:
                        db.rollback()
                        log_event(db, "ERROR", f"Background job failed: {exc}")
                        db.commit()
                except Exception:
                    pass
            finally:
                if db:
                    db.close()

    t = threading.Thread(target=loop, daemon=True, name="planner-jobs")
    t.start()
    return t
