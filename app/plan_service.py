"""Connects the planning engine (S4) to the database.

regenerate_plan()  -> UC-05 / UC-07 / FR-19 (used after tasks or free time change)
handle_missed()    -> UC-09 / FR-18 to FR-20
check_unmarked()   -> FR-18 background check
"""
import datetime as dt

from . import notifications as notify
from .planning.priority import priority_score
from .planning.reschedule import is_unmarked, reschedule_missed
from .planning.scheduler import build_free_slots, generate_plan
from .timeutil import fmt, parse, week_start

ACTIVE = ("planned", "rescheduled")


def _student(db, student_id):
    return db.query("SELECT s.*, u.email, u.full_name FROM students s JOIN users u ON u.user_id = s.user_id "
                    "WHERE s.user_id = ?", (student_id,), one=True)


def _minutes(s):
    return int((parse(s["planned_end"]) - parse(s["planned_start"])).total_seconds() // 60)


def _blocks_and_busy(db, student_id):
    blocks = db.query("SELECT day_of_week, start_time, end_time FROM availability_blocks WHERE student_id = ?",
                      (student_id,))
    busy = [(parse(b["start_at"]), parse(b["end_at"]))
            for b in db.query("SELECT start_at, end_at FROM busy_events WHERE student_id = ?", (student_id,))]
    return blocks, busy


def _plan_id(db, student_id, day, now):
    ws = week_start(day).isoformat()
    row = db.query("SELECT plan_id FROM study_plans WHERE student_id = ? AND week_start = ?", (student_id, ws), one=True)
    if row:
        db.execute("UPDATE study_plans SET generated_at = ? WHERE plan_id = ?", (fmt(now), row["plan_id"]))
        return row["plan_id"]
    return db.execute("INSERT INTO study_plans (student_id, week_start, generated_at) VALUES (?, ?, ?)",
                      (student_id, ws, fmt(now)))


def _sessions_for_student(db, student_id):
    return db.query(
        "SELECT ss.*, t.title, t.task_type, t.deadline, c.course_code FROM study_sessions ss "
        "JOIN tasks t ON t.task_id = ss.task_id JOIN courses c ON c.course_id = t.course_id "
        "WHERE c.student_id = ?", (student_id,))


def update_priorities(db, student_id, now):
    for t in db.query("SELECT t.task_id, t.grade_weight, t.difficulty, t.deadline FROM tasks t "
                      "JOIN courses c ON c.course_id = t.course_id WHERE c.student_id = ? AND t.status <> 'done'",
                      (student_id,)):
        score = priority_score(float(t["grade_weight"]), int(t["difficulty"]), parse(t["deadline"]), now)
        db.execute("UPDATE tasks SET priority_score = ? WHERE task_id = ?", (score, t["task_id"]))


def regenerate_plan(db, student_id, now):
    """Rebuild future sessions. Completed, partly completed, missed and locked sessions are kept (FR-16, FR-19)."""
    student = _student(db, student_id)
    blocks, busy = _blocks_and_busy(db, student_id)
    if not blocks:
        return {"ok": False, "error": "Please set your weekly free time first.", "code": "NO_AVAILABILITY"}

    # Remove future sessions that are only planned, so they can be placed again.
    for s in _sessions_for_student(db, student_id):
        if s["status"] in ACTIVE and not s["is_locked"] and parse(s["planned_start"]) >= now:
            notify.cancel_session_reminders(db, s["session_id"])
            db.execute("DELETE FROM study_sessions WHERE session_id = ?", (s["session_id"],))

    kept, done_minutes = [], {}
    for s in _sessions_for_student(db, student_id):
        mins = _minutes(s)
        if s["status"] == "completed":
            done_minutes[s["task_id"]] = done_minutes.get(s["task_id"], 0) + mins
        elif s["status"] == "partly_completed":
            done_minutes[s["task_id"]] = done_minutes.get(s["task_id"], 0) + mins // 2
        elif s["status"] in ACTIVE and s["session_type"] == "study":   # locked or still running
            done_minutes[s["task_id"]] = done_minutes.get(s["task_id"], 0) + mins
        if s["status"] != "missed" and parse(s["planned_end"]) > now:
            kept.append((parse(s["planned_start"]), parse(s["planned_end"])))

    tasks = db.query("SELECT t.*, c.course_code FROM tasks t JOIN courses c ON c.course_id = t.course_id "
                     "WHERE c.student_id = ? AND t.status <> 'done'", (student_id,))
    plan_tasks = []
    for t in tasks:
        total = int(float(t["estimated_hours"]) * 60)
        plan_tasks.append({
            "task_id": t["task_id"], "task_type": t["task_type"], "deadline": parse(t["deadline"]),
            "grade_weight": float(t["grade_weight"]), "difficulty": int(t["difficulty"]),
            "remaining_minutes": max(total - done_minutes.get(t["task_id"], 0), 0),
        })

    sessions, at_risk = generate_plan(now, plan_tasks, blocks, busy, kept,
                                      float(student["daily_study_limit"]), int(student["session_length"]))
    titles = {t["task_id"]: (t["course_code"], t["title"]) for t in tasks}
    for s in sessions:
        sid = db.execute(
            "INSERT INTO study_sessions (task_id, plan_id, session_type, review_offset_days, planned_start, planned_end, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'planned')",
            (s["task_id"], _plan_id(db, student_id, s["start"], now), s["session_type"], s["review_offset_days"],
             fmt(s["start"]), fmt(s["end"])))
        code, title = titles[s["task_id"]]
        notify.schedule_reminder(db, student, {"session_id": sid, "planned_start": fmt(s["start"]),
                                               "session_type": s["session_type"]}, code, title)
    for t in tasks:
        db.execute("UPDATE tasks SET at_risk = ? WHERE task_id = ?", (1 if t["task_id"] in at_risk else 0, t["task_id"]))
    update_priorities(db, student_id, now)
    warnings = [{"task_id": tid, "course_code": titles[tid][0], "title": titles[tid][1], "shortfall_hours": h}
                for tid, h in at_risk.items()]
    return {"ok": True, "sessions_created": len(sessions),
            "review_sessions": sum(1 for s in sessions if s["session_type"] == "review"), "at_risk": warnings}


def handle_missed(db, session_id, now, timeout=False):
    """UC-09: mark a session as missed and move it, split it, or tell the student there is no slot."""
    s = db.query("SELECT ss.*, t.deadline, t.title, c.course_code, c.student_id FROM study_sessions ss "
                 "JOIN tasks t ON t.task_id = ss.task_id JOIN courses c ON c.course_id = t.course_id "
                 "WHERE ss.session_id = ?", (session_id,), one=True)
    student = _student(db, s["student_id"])
    notify.cancel_session_reminders(db, session_id)
    db.execute("UPDATE study_sessions SET status = 'missed' WHERE session_id = ?", (session_id,))
    if s["is_locked"]:
        return {"action": "recorded", "message": "This locked session was recorded as missed."}

    deadline = parse(s["deadline"])
    blocks, busy = _blocks_and_busy(db, s["student_id"])
    occupied, usage = [], {}
    for o in _sessions_for_student(db, s["student_id"]):
        if o["session_id"] == session_id or o["status"] == "missed":
            continue
        st, en = parse(o["planned_start"]), parse(o["planned_end"])
        occupied.append((st, en))
        usage[st.date()] = usage.get(st.date(), 0) + _minutes(o)
    # Search from now, or from the end of the missed slot if it is still in the future (never the same slot again).
    base = max(now, parse(s["planned_end"])).replace(second=0, microsecond=0)
    start = base + dt.timedelta(minutes=(5 - base.minute % 5) % 5)
    slots = build_free_slots(start, deadline, blocks, busy, occupied)
    result = reschedule_missed(_minutes(s), slots, deadline, usage, int(float(student["daily_study_limit"]) * 60))

    name = f"{s['course_code']} {s['title']}"
    if result["action"] == "moved":
        db.execute("UPDATE study_sessions SET planned_start = ?, planned_end = ?, status = 'rescheduled', "
                   "reschedule_count = reschedule_count + 1, plan_id = ? WHERE session_id = ?",
                   (fmt(result["start"]), fmt(result["end"]), _plan_id(db, s["student_id"], result["start"], now), session_id))
        msg = f"Your {name} session has moved to {result['start']:%a %d %b, %H:%M}."
        notify.schedule_reminder(db, student, {"session_id": session_id, "planned_start": fmt(result["start"]),
                                               "session_type": s["session_type"]}, s["course_code"], s["title"])
        result = {"action": "moved", "new_start": fmt(result["start"]), "new_end": fmt(result["end"]), "message": msg}
    elif result["action"] == "split":
        (s1, e1), (s2, e2) = result["parts"]
        db.execute("UPDATE study_sessions SET planned_start = ?, planned_end = ?, status = 'rescheduled', "
                   "reschedule_count = reschedule_count + 1, plan_id = ? WHERE session_id = ?",
                   (fmt(s1), fmt(e1), _plan_id(db, s["student_id"], s1, now), session_id))
        new_id = db.execute(
            "INSERT INTO study_sessions (task_id, plan_id, session_type, review_offset_days, planned_start, planned_end, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'rescheduled')",
            (s["task_id"], _plan_id(db, s["student_id"], s2, now), s["session_type"], s["review_offset_days"], fmt(s2), fmt(e2)))
        for sid, st in ((session_id, s1), (new_id, s2)):
            notify.schedule_reminder(db, student, {"session_id": sid, "planned_start": fmt(st),
                                                   "session_type": s["session_type"]}, s["course_code"], s["title"])
        msg = f"Your {name} session was split into two parts: {s1:%a %H:%M} and {s2:%a %H:%M}."
        result = {"action": "split", "parts": [[fmt(s1), fmt(e1)], [fmt(s2), fmt(e2)]], "message": msg}
    else:
        msg = (f"There is no free time left before the deadline for {name}. "
               "You could raise your daily study limit or add more free time.")
        result = {"action": "none", "message": msg}
    notify.queue(db, s["student_id"], "update", msg, now, session_id=session_id)
    return result


def check_unmarked(db, now, timeout_hours=2):
    """FR-18: treat sessions with no status 2 hours after their end as missed."""
    handled = 0
    rows = db.query("SELECT session_id, status, planned_end FROM study_sessions WHERE status IN ('planned','rescheduled')")
    for r in rows:
        if is_unmarked({"status": r["status"], "planned_end": parse(r["planned_end"])}, now, timeout_hours):
            handle_missed(db, r["session_id"], now, timeout=True)
            handled += 1
    return handled
