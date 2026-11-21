"""Progress & Sharing routes (S6): UC-11 to UC-13, FR-23, FR-25, FR-26."""
import datetime as dt

from flask import Blueprint, g, jsonify, request

from ..db import get_db
from ..progress import advisor_view, summary
from ..security import auth_required, error, log_event
from ..timeutil import fmt, now, parse, week_start

bp = Blueprint("progress", __name__, url_prefix="/api")


@bp.get("/progress")
@auth_required("student")
def progress():
    db, t = get_db(), now()
    w = request.args.get("week")
    data = summary(db, g.user["user_id"], t, week_start(dt.date.fromisoformat(w)) if w else None)
    data["upcoming"] = db.query(
        "SELECT t.title, t.deadline, t.task_type, c.course_code FROM tasks t JOIN courses c ON c.course_id = t.course_id "
        "WHERE c.student_id = ? AND t.status <> 'done' AND t.deadline >= ? ORDER BY t.deadline LIMIT 5",
        (g.user["user_id"], fmt(t)))
    return jsonify(data)


# ---------- student side (UC-12) ----------
@bp.get("/sharing")
@auth_required("student")
def sharing_status():
    db = get_db()
    history = db.query("SELECT sc.*, u.full_name AS advisor_name, a.department FROM sharing_consents sc "
                       "JOIN users u ON u.user_id = sc.advisor_id JOIN advisors a ON a.user_id = sc.advisor_id "
                       "WHERE sc.student_id = ? ORDER BY sc.granted_at DESC", (g.user["user_id"],))
    return jsonify({"sharing_on": any(h["is_active"] for h in history), "history": history,
                    "shared_fields": ["Session completion rate", "Study streak", "Number of overdue tasks"]})


@bp.get("/advisors")
@auth_required("student")
def search_advisors():
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    return jsonify(get_db().query(
        "SELECT u.user_id, u.full_name, u.email, a.department FROM users u JOIN advisors a ON a.user_id = u.user_id "
        "WHERE u.status = 'active' AND (LOWER(u.full_name) LIKE ? OR LOWER(u.email) LIKE ?) ORDER BY u.full_name LIMIT 10",
        (f"%{q}%", f"%{q}%")))


@bp.post("/sharing")
@auth_required("student")
def grant():
    """FR-25: record consent with the date and time, then give read-only access."""
    db = get_db()
    advisor_id = (request.get_json(silent=True) or {}).get("advisor_id")
    adv = db.query("SELECT u.user_id, u.full_name FROM users u JOIN advisors a ON a.user_id = u.user_id WHERE u.user_id = ?",
                   (advisor_id,), one=True)
    if not adv:
        return error("Advisor not found.", 404)
    if db.query("SELECT 1 AS x FROM sharing_consents WHERE student_id = ? AND advisor_id = ? AND is_active = 1",
                (g.user["user_id"], advisor_id), one=True):
        return error("You are already sharing with this advisor.", 409)
    cid = db.execute("INSERT INTO sharing_consents (student_id, advisor_id, is_active, granted_at) VALUES (?, ?, 1, ?)",
                     (g.user["user_id"], advisor_id, fmt(now())))
    log_event(db, "INFO", f"Sharing granted to advisor {advisor_id}", g.user["user_id"])
    db.commit()
    return jsonify({"consent_id": cid, "message": f"Your progress summary is now shared with {adv['full_name']}."}), 201


@bp.delete("/sharing/<int:consent_id>")
@auth_required("student")
def revoke(consent_id):
    """Turning sharing off removes access straight away."""
    db = get_db()
    c = db.query("SELECT * FROM sharing_consents WHERE consent_id = ? AND student_id = ?",
                 (consent_id, g.user["user_id"]), one=True)
    if not c or not c["is_active"]:
        return error("Active sharing not found.", 404)
    db.execute("UPDATE sharing_consents SET is_active = 0, revoked_at = ? WHERE consent_id = ?", (fmt(now()), consent_id))
    log_event(db, "INFO", f"Sharing revoked for advisor {c['advisor_id']}", g.user["user_id"])
    db.commit()
    return jsonify({"message": "Sharing turned off. Your advisor can no longer see your summary."})


# ---------- advisor side (UC-13) ----------
@bp.get("/advisor/students")
@auth_required("advisor")
def my_students():
    db, t = get_db(), now()
    rows = db.query("SELECT u.user_id, u.full_name, MAX(sc.is_active) AS sharing FROM sharing_consents sc "
                    "JOIN users u ON u.user_id = sc.student_id WHERE sc.advisor_id = ? GROUP BY u.user_id, u.full_name "
                    "ORDER BY u.full_name", (g.user["user_id"],))
    for r in rows:
        r["sharing"] = bool(r["sharing"])
        if r["sharing"]:
            v = advisor_view(db, r["user_id"], t)
            r["completion_rate"], r["overdue_tasks"] = v["completion_rate"], v["overdue_tasks"]
    return jsonify(rows)


@bp.get("/advisor/students/<int:student_id>/summary")
@auth_required("advisor")
def student_summary(student_id):
    """FR-26 / NFR-10: refused unless the student has an active consent for this advisor."""
    db = get_db()
    ok = db.query("SELECT 1 AS x FROM sharing_consents WHERE student_id = ? AND advisor_id = ? AND is_active = 1",
                  (student_id, g.user["user_id"]), one=True)
    if not ok:
        log_event(db, "WARN", f"Advisor access denied for student {student_id}", g.user["user_id"])
        db.commit()
        return error("Access denied: this student is not sharing progress with you.", 403)
    name = db.query("SELECT full_name FROM users WHERE user_id = ?", (student_id,), one=True)["full_name"]
    data = advisor_view(db, student_id, now())
    data["student_name"] = name
    return jsonify(data)
