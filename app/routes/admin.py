"""Administration routes (S7): UC-14, FR-27, FR-28."""
from flask import Blueprint, g, jsonify, request

from ..db import get_db
from ..jobs import run_all
from ..security import auth_required, error, log_event
from ..timeutil import now

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/users")
@auth_required("admin")
def users():
    q = f"%{(request.args.get('q') or '').strip().lower()}%"
    sql, params = ("SELECT user_id, full_name, email, role, status, created_at FROM users "
                   "WHERE (LOWER(full_name) LIKE ? OR LOWER(email) LIKE ?)"), [q, q]
    for key in ("role", "status"):
        if request.args.get(key):
            sql += f" AND {key} = ?"
            params.append(request.args[key])
    return jsonify(get_db().query(sql + " ORDER BY role, full_name", params))


@bp.patch("/users/<int:user_id>")
@auth_required("admin")
def set_status(user_id):
    """Deactivate, reactivate or unlock an account."""
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("active", "deactivated"):
        return error("Status must be active or deactivated.", 400)
    if user_id == g.user["user_id"]:
        return error("You cannot change your own account here.", 400)
    db = get_db()
    if not db.query("SELECT 1 AS x FROM users WHERE user_id = ?", (user_id,), one=True):
        return error("User not found.", 404)
    db.execute("UPDATE users SET status = ?, failed_login_count = 0, locked_until = NULL WHERE user_id = ?", (status, user_id))
    log_event(db, "INFO", f"Admin set user {user_id} to {status}", g.user["user_id"])
    db.commit()
    return jsonify({"user_id": user_id, "status": status})


@bp.delete("/users/<int:user_id>")
@auth_required("admin")
def delete_user(user_id):
    if user_id == g.user["user_id"]:
        return error("You cannot delete your own account here.", 400)
    db = get_db()
    db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    log_event(db, "INFO", f"Admin deleted user {user_id}", g.user["user_id"])
    db.commit()
    return jsonify({"message": "User deleted."})


@bp.get("/stats")
@auth_required("admin")
def stats():
    db = get_db()
    one = lambda sql: db.query(sql, one=True)["n"]  # noqa: E731
    sent = one("SELECT COUNT(*) AS n FROM notifications WHERE delivery_status = 'sent'")
    failed = one("SELECT COUNT(*) AS n FROM notifications WHERE delivery_status = 'failed'")
    return jsonify({
        "registered_users": one("SELECT COUNT(*) AS n FROM users"),
        "students": one("SELECT COUNT(*) AS n FROM users WHERE role = 'student'"),
        "locked_or_deactivated": one("SELECT COUNT(*) AS n FROM users WHERE status <> 'active'"),
        "plans_generated": one("SELECT COUNT(*) AS n FROM study_plans"),
        "sessions_planned": one("SELECT COUNT(*) AS n FROM study_sessions"),
        "notifications_sent": sent,
        "delivery_rate": round(100 * sent / (sent + failed), 1) if (sent + failed) else 100.0,
    })


@bp.get("/logs")
@auth_required("admin")
def logs():
    return jsonify(get_db().query("SELECT * FROM system_logs ORDER BY log_id DESC LIMIT 50"))


@bp.post("/run-jobs")
@auth_required("admin")
def run_jobs():
    """Runs the background jobs now (useful for the live demo)."""
    db = get_db()
    result = run_all(db, now())
    db.commit()
    return jsonify(result)
