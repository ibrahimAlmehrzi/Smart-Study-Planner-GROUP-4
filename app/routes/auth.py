"""Account & Access routes (S2): UC-01, FR-01 to FR-04, FR-30."""
import csv
import datetime as dt
import io
import re

import jwt
from flask import Blueprint, Response, current_app, g, jsonify, request

from ..db import get_db
from ..notifications import NotificationGateway
from ..security import auth_required, check_password, error, hash_password, log_event, make_token, read_token
from ..timeutil import fmt, now, parse

bp = Blueprint("auth", __name__, url_prefix="/api")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _password_problem(pw):
    if len(pw or "") < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must be at least 8 characters and include letters and numbers."
    return None


def public_user(u):
    return {"user_id": u["user_id"], "full_name": u["full_name"], "email": u["email"], "role": u["role"]}


@bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    name, email, pw = (data.get("full_name") or "").strip(), (data.get("email") or "").strip().lower(), data.get("password") or ""
    errors = {}
    if not name:
        errors["full_name"] = "Please enter your name."
    if not EMAIL_RE.match(email):
        errors["email"] = "Please enter a valid email address."
    if _password_problem(pw):
        errors["password"] = _password_problem(pw)
    db = get_db()
    if not errors and db.query("SELECT 1 AS x FROM users WHERE email = ?", (email,), one=True):
        errors["email"] = "An account with this email already exists."
    if errors:
        return error("Please correct the highlighted fields.", 400, fields=errors)
    # Prototype: email verification (FR-01) is marked as done at once; see README "Known limitations".
    uid = db.execute("INSERT INTO users (full_name, email, password_hash, role, status, email_verified, created_at) "
                     "VALUES (?, ?, ?, 'student', 'active', 1, ?)", (name, email, hash_password(pw), fmt(now())))
    db.execute("INSERT INTO students (user_id) VALUES (?)", (uid,))
    log_event(db, "INFO", f"New student account {email}", uid)
    db.commit()
    user = db.query("SELECT * FROM users WHERE user_id = ?", (uid,), one=True)
    return jsonify({"token": make_token(user), "user": public_user(user)}), 201


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email, pw = (data.get("email") or "").strip().lower(), data.get("password") or ""
    db, cfg, t = get_db(), current_app.config, now()
    user = db.query("SELECT * FROM users WHERE email = ?", (email,), one=True)
    if not user:
        return error("Incorrect email or password.", 401)
    if user["status"] == "deactivated":
        return error("This account has been deactivated. Please contact support.", 403)
    if user["status"] == "locked":
        if user["locked_until"] and parse(user["locked_until"]) > t:
            mins = int((parse(user["locked_until"]) - t).total_seconds() // 60) + 1
            return error(f"Too many failed attempts. Try again in {mins} minute(s).", 423)
        db.execute("UPDATE users SET status = 'active', failed_login_count = 0, locked_until = NULL WHERE user_id = ?",
                   (user["user_id"],))
    if not check_password(user["password_hash"], pw):
        fails = int(user["failed_login_count"] or 0) + 1
        if fails >= cfg["MAX_FAILED_LOGINS"]:
            until = t + dt.timedelta(minutes=cfg["LOCK_MINUTES"])
            db.execute("UPDATE users SET failed_login_count = 0, status = 'locked', locked_until = ? WHERE user_id = ?",
                       (fmt(until), user["user_id"]))
            log_event(db, "WARN", f"Account {email} locked after {fails} failed logins", user["user_id"])
            db.commit()
            return error(f"Too many failed attempts. Your account is locked for {cfg['LOCK_MINUTES']} minutes.", 423)
        db.execute("UPDATE users SET failed_login_count = ? WHERE user_id = ?", (fails, user["user_id"]))
        db.commit()
        left = cfg["MAX_FAILED_LOGINS"] - fails
        return error(f"Incorrect email or password. {left} attempt(s) left before the account is locked for "
                     f"{cfg['LOCK_MINUTES']} minutes.", 401, attempts_left=left)
    db.execute("UPDATE users SET failed_login_count = 0 WHERE user_id = ?", (user["user_id"],))
    db.commit()
    user = db.query("SELECT * FROM users WHERE user_id = ?", (user["user_id"],), one=True)
    return jsonify({"token": make_token(user), "user": public_user(user)})


@bp.post("/auth/forgot-password")
def forgot_password():
    """FR-03: a single-use reset link valid for 30 minutes (sent through the notification gateway)."""
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    db = get_db()
    user = db.query("SELECT * FROM users WHERE email = ?", (email,), one=True)
    if user:
        token = make_token(user, purpose="reset:" + user["password_hash"][-12:],
                           minutes=current_app.config["RESET_TOKEN_MINUTES"])
        NotificationGateway.send(email, f"Reset your password: /index.html?reset={token}")
    # Same answer either way, so the form does not reveal which emails exist.
    return jsonify({"message": "If the email is registered, a reset link has been sent."})


@bp.post("/auth/reset-password")
def reset_password():
    data = request.get_json(silent=True) or {}
    token, pw = data.get("token") or "", data.get("password") or ""
    if _password_problem(pw):
        return error(_password_problem(pw), 400)
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return error("This reset link is invalid or has expired.", 400)
    db = get_db()
    user = db.query("SELECT * FROM users WHERE user_id = ?", (int(payload["sub"]),), one=True)
    # Single use: the token is tied to the current password hash, so it stops working once used.
    if not user or payload.get("purpose") != "reset:" + user["password_hash"][-12:]:
        return error("This reset link is invalid or has expired.", 400)
    db.execute("UPDATE users SET password_hash = ?, failed_login_count = 0, status = 'active', locked_until = NULL "
               "WHERE user_id = ?", (hash_password(pw), user["user_id"]))
    db.commit()
    return jsonify({"message": "Your password has been changed. You can now log in."})


@bp.get("/me")
@auth_required()
def me():
    out = public_user(g.user)
    if g.user["role"] == "student":
        out["settings"] = get_db().query("SELECT daily_study_limit, session_length, reminder_lead_time, quiet_hours_start, "
                                         "quiet_hours_end FROM students WHERE user_id = ?", (g.user["user_id"],), one=True)
    return jsonify(out)


@bp.get("/me/export")
@auth_required("student")
def export_data():
    """FR-30: download all personal data as CSV."""
    db, uid = get_db(), g.user["user_id"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "course", "item", "type", "start_or_deadline", "end", "status", "grade_weight"])
    for t in db.query("SELECT c.course_code, t.title, t.task_type, t.deadline, t.status, t.grade_weight FROM tasks t "
                      "JOIN courses c ON c.course_id = t.course_id WHERE c.student_id = ?", (uid,)):
        w.writerow(["task", t["course_code"], t["title"], t["task_type"], t["deadline"], "", t["status"], t["grade_weight"]])
    for s in db.query("SELECT c.course_code, t.title, ss.session_type, ss.planned_start, ss.planned_end, ss.status "
                      "FROM study_sessions ss JOIN tasks t ON t.task_id = ss.task_id JOIN courses c ON c.course_id = t.course_id "
                      "WHERE c.student_id = ? ORDER BY ss.planned_start", (uid,)):
        w.writerow(["session", s["course_code"], s["title"], s["session_type"], s["planned_start"], s["planned_end"], s["status"], ""])
    for c in db.query("SELECT u.full_name, sc.granted_at, sc.revoked_at, sc.is_active FROM sharing_consents sc "
                      "JOIN users u ON u.user_id = sc.advisor_id WHERE sc.student_id = ?", (uid,)):
        w.writerow(["consent", "", c["full_name"], "advisor", c["granted_at"], c["revoked_at"] or "",
                    "active" if c["is_active"] else "revoked", ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=my_study_data.csv"})


@bp.delete("/me")
@auth_required("student")
def delete_account():
    """FR-30: permanently delete the account and all related data (cascades through the foreign keys)."""
    db = get_db()
    db.execute("DELETE FROM users WHERE user_id = ?", (g.user["user_id"],))
    db.commit()
    return jsonify({"message": "Your account and all related data have been deleted."})
