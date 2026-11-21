"""Planning routes (S4): UC-05 to UC-09, UC-15, FR-11 to FR-20, FR-29."""
import datetime as dt

from flask import Blueprint, Response, g, jsonify, request

from ..db import get_db
from ..plan_service import handle_missed, regenerate_plan, update_priorities
from ..planning.priority import explain_priority, priority_score, rank_tasks
from ..security import auth_required, error, log_event
from ..timeutil import now, parse, week_start

bp = Blueprint("plans", __name__, url_prefix="/api")


def _week_param():
    w = request.args.get("week")
    return week_start(dt.date.fromisoformat(w)) if w else week_start(now())


def _own_session(db, session_id):
    return db.query("SELECT ss.* FROM study_sessions ss JOIN tasks t ON t.task_id = ss.task_id "
                    "JOIN courses c ON c.course_id = t.course_id WHERE ss.session_id = ? AND c.student_id = ?",
                    (session_id, g.user["user_id"]), one=True)


@bp.get("/tasks/ranked")
@auth_required("student")
def ranked():
    """FR-12: open tasks from highest to lowest priority, with a short reason."""
    db, t = get_db(), now()
    rows = db.query("SELECT t.*, c.course_code FROM tasks t JOIN courses c ON c.course_id = t.course_id "
                    "WHERE c.student_id = ? AND t.status <> 'done'", (g.user["user_id"],))
    for r in rows:
        r["deadline_dt"] = parse(r["deadline"])
    out = []
    for r in rank_tasks([{**r, "deadline": r["deadline_dt"]} for r in rows], t):
        out.append({"task_id": r["task_id"], "course_code": r["course_code"], "title": r["title"],
                    "task_type": r["task_type"], "deadline": r["deadline"].strftime("%Y-%m-%d %H:%M:%S"),
                    "score": priority_score(r["grade_weight"], r["difficulty"], r["deadline"], t),
                    "reason": explain_priority(r, t), "at_risk": bool(r["at_risk"])})
    return jsonify(out)


@bp.post("/plans/generate")
@auth_required("student")
def generate():
    db = get_db()
    result = regenerate_plan(db, g.user["user_id"], now())
    if not result["ok"]:
        return error(result["error"], 400, code=result["code"])
    log_event(db, "INFO", f"Plan generated: {result['sessions_created']} sessions", g.user["user_id"])
    db.commit()
    return jsonify(result)


@bp.get("/plans")
@auth_required("student")
def week_plan():
    db, ws = get_db(), _week_param()
    we = ws + dt.timedelta(days=7)
    sessions = db.query(
        "SELECT ss.*, t.title, t.task_type, t.deadline, t.grade_weight, t.difficulty, t.priority_score, c.course_code "
        "FROM study_sessions ss JOIN tasks t ON t.task_id = ss.task_id JOIN courses c ON c.course_id = t.course_id "
        "WHERE c.student_id = ? AND ss.planned_start >= ? AND ss.planned_start < ? ORDER BY ss.planned_start",
        (g.user["user_id"], ws.isoformat() + " 00:00:00", we.isoformat() + " 00:00:00"))
    at_risk = db.query("SELECT t.task_id, t.title, t.deadline, c.course_code FROM tasks t JOIN courses c ON c.course_id = t.course_id "
                       "WHERE c.student_id = ? AND t.at_risk = 1 AND t.status <> 'done'", (g.user["user_id"],))
    return jsonify({"week_start": ws.isoformat(), "sessions": sessions, "at_risk": at_risk})


@bp.patch("/sessions/<int:session_id>/status")
@auth_required("student")
def set_status(session_id):
    """FR-17: completed, partly completed or missed. Missed sessions are rescheduled at once (FR-18)."""
    db = get_db()
    s = _own_session(db, session_id)
    if not s:
        return error("Session not found.", 404)
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("completed", "partly_completed", "missed"):
        return error("Status must be completed, partly_completed or missed.", 400)
    if status == "missed":
        result = handle_missed(db, session_id, now())
    else:
        db.execute("UPDATE study_sessions SET status = ? WHERE session_id = ?", (status, session_id))
        db.execute("DELETE FROM notifications WHERE session_id = ? AND type = 'reminder' AND delivery_status = 'pending'",
                   (session_id,))
        result = {"action": status, "message": "Well done, your progress has been updated."
                  if status == "completed" else "Progress saved."}
    update_priorities(db, g.user["user_id"], now())
    db.commit()
    return jsonify(result)


@bp.patch("/sessions/<int:session_id>/lock")
@auth_required("student")
def lock(session_id):
    """FR-16: locked sessions are never moved automatically."""
    db = get_db()
    if not _own_session(db, session_id):
        return error("Session not found.", 404)
    locked = bool((request.get_json(silent=True) or {}).get("locked", True))
    db.execute("UPDATE study_sessions SET is_locked = ? WHERE session_id = ?", (1 if locked else 0, session_id))
    db.commit()
    return jsonify({"session_id": session_id, "is_locked": locked})


@bp.get("/plans/export.ics")
@auth_required("student")
def export_ics():
    """FR-29: weekly timetable as an iCalendar file for Google Calendar or Outlook."""
    db, ws = get_db(), _week_param()
    we = ws + dt.timedelta(days=7)
    rows = db.query(
        "SELECT ss.*, t.title, c.course_code FROM study_sessions ss JOIN tasks t ON t.task_id = ss.task_id "
        "JOIN courses c ON c.course_id = t.course_id WHERE c.student_id = ? AND ss.status <> 'missed' "
        "AND ss.planned_start >= ? AND ss.planned_start < ? ORDER BY ss.planned_start",
        (g.user["user_id"], ws.isoformat() + " 00:00:00", we.isoformat() + " 00:00:00"))
    stamp = now().strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Smart Study Planner//Group 4//EN", "CALSCALE:GREGORIAN"]
    for r in rows:
        label = "Review" if r["session_type"] == "review" else "Study"
        lines += ["BEGIN:VEVENT", f"UID:session-{r['session_id']}@smartstudyplanner", f"DTSTAMP:{stamp}",
                  f"DTSTART:{parse(r['planned_start']):%Y%m%dT%H%M%S}", f"DTEND:{parse(r['planned_end']):%Y%m%dT%H%M%S}",
                  f"SUMMARY:{label}: {r['course_code']} {r['title']}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename=study_plan_{ws.isoformat()}.ics"})
