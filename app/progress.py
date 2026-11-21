"""ProgressController (UC-11, UC-13, FR-23, FR-24)."""
import datetime as dt

from .timeutil import fmt, parse, week_start


def _sessions(db, student_id):
    return db.query("SELECT ss.status, ss.planned_start, ss.planned_end, c.course_code FROM study_sessions ss "
                    "JOIN tasks t ON t.task_id = ss.task_id JOIN courses c ON c.course_id = t.course_id "
                    "WHERE c.student_id = ?", (student_id,))


def _credit(status):
    return {"completed": 1.0, "partly_completed": 0.5}.get(status, 0.0)


def streak(sessions, today):
    """Number of days in a row, ending today or yesterday, with at least one completed session."""
    days = {parse(s["planned_start"]).date() for s in sessions if s["status"] in ("completed", "partly_completed")}
    day = today if today in days else today - dt.timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= dt.timedelta(days=1)
    return count


def week_figures(sessions, ws, now):
    we = ws + dt.timedelta(days=7)
    in_week = [s for s in sessions if ws <= parse(s["planned_start"]).date() < we]
    planned = len(in_week)
    due = [s for s in in_week if parse(s["planned_end"]) <= now or s["status"] in ("completed", "partly_completed", "missed")]
    done = sum(_credit(s["status"]) for s in due)
    rate = round(100 * done / len(due), 1) if due else 0.0
    return {"week_start": ws.isoformat(), "planned": planned, "completed": done, "due": len(due), "completion_rate": rate}


def summary(db, student_id, now, week=None):
    sessions = _sessions(db, student_id)
    ws = week or week_start(now)
    current = week_figures(sessions, ws, now)
    overdue = db.query("SELECT COUNT(*) AS n FROM tasks t JOIN courses c ON c.course_id = t.course_id "
                       "WHERE c.student_id = ? AND t.status <> 'done' AND t.deadline < ?", (student_id, fmt(now)), one=True)["n"]
    return {
        "week": current,
        "streak": streak(sessions, now.date()),
        "overdue_tasks": int(overdue),
        "history": [week_figures(sessions, ws - dt.timedelta(weeks=k), now) for k in range(4, -1, -1)],
        "by_course": _by_course(sessions, now),
    }


def _by_course(sessions, now):
    out = {}
    for s in sessions:
        if parse(s["planned_end"]) > now and s["status"] not in ("completed", "partly_completed", "missed"):
            continue
        c = out.setdefault(s["course_code"], [0, 0.0])
        c[0] += 1
        c[1] += _credit(s["status"])
    return [{"course_code": k, "completion_rate": round(100 * v[1] / v[0], 1)} for k, v in sorted(out.items()) if v[0]]


def advisor_view(db, student_id, now):
    """FR-26: only completion rate, streak and overdue tasks (this week and last week)."""
    full = summary(db, student_id, now)
    last = full["history"][-2]
    return {
        "completion_rate": full["week"]["completion_rate"], "last_week_completion_rate": last["completion_rate"],
        "streak": full["streak"], "overdue_tasks": full["overdue_tasks"],
        "trend": [{"week_start": h["week_start"], "completion_rate": h["completion_rate"]} for h in full["history"]],
    }


def store_weekly_summary(db, student_id, now):
    """FR-24: save last week's figures (run by the background job on Sundays)."""
    s = summary(db, student_id, now)
    w = s["week"]
    exists = db.query("SELECT summary_id FROM progress_summaries WHERE student_id = ? AND week_start = ?",
                      (student_id, w["week_start"]), one=True)
    values = (w["planned"], int(w["completed"]), w["completion_rate"], s["streak"], s["overdue_tasks"])
    if exists:
        db.execute("UPDATE progress_summaries SET planned_sessions = ?, completed_sessions = ?, completion_rate = ?, "
                   "streak = ?, overdue_tasks = ? WHERE summary_id = ?", values + (exists["summary_id"],))
    else:
        db.execute("INSERT INTO progress_summaries (planned_sessions, completed_sessions, completion_rate, streak, "
                   "overdue_tasks, student_id, week_start) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   values + (student_id, w["week_start"]))
    return s
