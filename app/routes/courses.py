"""Course, Task & Availability routes (S3): UC-02, UC-03, UC-04, FR-05 to FR-10, FR-19."""
from flask import Blueprint, g, jsonify, request

from ..db import get_db
from ..plan_service import regenerate_plan, update_priorities
from ..security import auth_required, error
from ..timeutil import fmt, now, parse, parse_time

bp = Blueprint("courses", __name__, url_prefix="/api")
TASK_TYPES = ("assignment", "exam", "quiz", "project", "reading")


# ---------- helpers ----------
def _own_course(db, course_id):
    return db.query("SELECT * FROM courses WHERE course_id = ? AND student_id = ?", (course_id, g.user["user_id"]), one=True)


def _own_task(db, task_id):
    return db.query("SELECT t.* FROM tasks t JOIN courses c ON c.course_id = t.course_id "
                    "WHERE t.task_id = ? AND c.student_id = ?", (task_id, g.user["user_id"]), one=True)


def _has_plan(db):
    return db.query("SELECT 1 AS x FROM study_sessions ss JOIN tasks t ON t.task_id = ss.task_id "
                    "JOIN courses c ON c.course_id = t.course_id WHERE c.student_id = ? LIMIT 1",
                    (g.user["user_id"],), one=True) is not None


def _after_change(db):
    """FR-19: when a plan already exists, update it (completed and locked sessions are kept)."""
    if _has_plan(db):
        return regenerate_plan(db, g.user["user_id"], now())
    update_priorities(db, g.user["user_id"], now())
    return None


def validate_task(data, current_time, partial=False):
    """FR-07: grade weight 0-100, difficulty 1-5, deadline not in the past, estimated hours > 0."""
    errors, clean = {}, {}
    def has(k):
        return k in data and data[k] not in (None, "")
    if has("title") or not partial:
        title = (data.get("title") or "").strip()
        if not title:
            errors["title"] = "Please enter a title."
        elif len(title) > 150:
            errors["title"] = "Title must be 150 characters or fewer."
        clean["title"] = title
    if has("task_type") or not partial:
        if data.get("task_type") not in TASK_TYPES:
            errors["task_type"] = "Choose assignment, exam, quiz, project or reading."
        clean["task_type"] = data.get("task_type")
    if has("deadline") or not partial:
        try:
            d = parse(data.get("deadline"))
            if d <= current_time:
                errors["deadline"] = "The deadline cannot be in the past."
            clean["deadline"] = fmt(d)
        except (TypeError, ValueError):
            errors["deadline"] = "Please enter a valid date and time."
    for key, lo, hi, cast, msg in (
        ("grade_weight", 0, 100, float, "Must be between 0 and 100"),
        ("difficulty", 1, 5, int, "Must be between 1 and 5"),
    ):
        if has(key) or not partial:
            try:
                v = cast(data.get(key))
                if not lo <= v <= hi:
                    raise ValueError
                clean[key] = v
            except (TypeError, ValueError):
                errors[key] = msg
    if has("estimated_hours") or not partial:
        try:
            h = float(data.get("estimated_hours"))
            if not 0 < h <= 200:
                raise ValueError
            clean["estimated_hours"] = h
        except (TypeError, ValueError):
            errors["estimated_hours"] = "Must be more than 0 hours"
    if "status" in data:
        if data["status"] not in ("pending", "in_progress", "done"):
            errors["status"] = "Unknown status"
        clean["status"] = data["status"]
    return errors, clean


def _weight_warning(db, course_id):
    total = db.query("SELECT COALESCE(SUM(grade_weight), 0) AS s FROM tasks WHERE course_id = ?", (course_id,), one=True)["s"]
    total = float(total)
    if total > 100:
        code = db.query("SELECT course_code FROM courses WHERE course_id = ?", (course_id,), one=True)["course_code"]
        return f"The total grade weight of {code} tasks is {total:g}%. Please check the weights."
    return None


# ---------- courses (FR-05) ----------
@bp.get("/courses")
@auth_required("student")
def list_courses():
    db = get_db()
    rows = db.query("SELECT * FROM courses WHERE student_id = ? ORDER BY course_code", (g.user["user_id"],))
    for c in rows:
        c["total_weight"] = float(db.query("SELECT COALESCE(SUM(grade_weight),0) AS s FROM tasks WHERE course_id = ?",
                                           (c["course_id"],), one=True)["s"])
    return jsonify(rows)


@bp.post("/courses")
@auth_required("student")
def add_course():
    data, db = request.get_json(silent=True) or {}, get_db()
    code, name = (data.get("course_code") or "").strip().upper(), (data.get("course_name") or "").strip()
    errors = {}
    if not code or len(code) > 20:
        errors["course_code"] = "Enter a course code of up to 20 characters."
    if not name:
        errors["course_name"] = "Enter the course name."
    try:
        credits = int(data.get("credit_hours", 3))
        if not 0 <= credits <= 6:
            raise ValueError
    except (TypeError, ValueError):
        errors["credit_hours"] = "Must be between 0 and 6"
    if not errors and db.query("SELECT 1 AS x FROM courses WHERE student_id = ? AND course_code = ?",
                               (g.user["user_id"], code), one=True):
        errors["course_code"] = "You already have this course."
    if errors:
        return error("Please correct the highlighted fields.", 400, fields=errors)
    cid = db.execute("INSERT INTO courses (student_id, course_code, course_name, credit_hours) VALUES (?, ?, ?, ?)",
                     (g.user["user_id"], code, name, credits))
    db.commit()
    return jsonify(db.query("SELECT * FROM courses WHERE course_id = ?", (cid,), one=True)), 201


@bp.put("/courses/<int:course_id>")
@auth_required("student")
def edit_course(course_id):
    db = get_db()
    c = _own_course(db, course_id)
    if not c:
        return error("Course not found.", 404)
    data = request.get_json(silent=True) or {}
    db.execute("UPDATE courses SET course_name = ?, credit_hours = ? WHERE course_id = ?",
               ((data.get("course_name") or c["course_name"]).strip(), int(data.get("credit_hours", c["credit_hours"])), course_id))
    db.commit()
    return jsonify(db.query("SELECT * FROM courses WHERE course_id = ?", (course_id,), one=True))


@bp.delete("/courses/<int:course_id>")
@auth_required("student")
def delete_course(course_id):
    db = get_db()
    if not _own_course(db, course_id):
        return error("Course not found.", 404)
    db.execute("DELETE FROM courses WHERE course_id = ?", (course_id,))   # tasks and sessions cascade
    _after_change(db)
    db.commit()
    return jsonify({"message": "Course deleted."})


# ---------- tasks (FR-06 to FR-08) ----------
@bp.get("/courses/<int:course_id>/tasks")
@auth_required("student")
def list_tasks(course_id):
    db = get_db()
    if not _own_course(db, course_id):
        return error("Course not found.", 404)
    return jsonify(db.query("SELECT * FROM tasks WHERE course_id = ? ORDER BY deadline", (course_id,)))


@bp.post("/courses/<int:course_id>/tasks")
@auth_required("student")
def add_task(course_id):
    db = get_db()
    if not _own_course(db, course_id):
        return error("Course not found.", 404)
    errors, t = validate_task(request.get_json(silent=True) or {}, now())
    if errors:
        return error("Please correct the highlighted fields.", 400, fields=errors)
    tid = db.execute("INSERT INTO tasks (course_id, title, task_type, deadline, grade_weight, difficulty, estimated_hours) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (course_id, t["title"], t["task_type"], t["deadline"], t["grade_weight"], t["difficulty"], t["estimated_hours"]))
    plan = _after_change(db)
    db.commit()
    return jsonify({"task": db.query("SELECT * FROM tasks WHERE task_id = ?", (tid,), one=True),
                    "warning": _weight_warning(db, course_id), "plan": plan}), 201


@bp.put("/tasks/<int:task_id>")
@auth_required("student")
def edit_task(task_id):
    db = get_db()
    task = _own_task(db, task_id)
    if not task:
        return error("Task not found.", 404)
    data = request.get_json(silent=True) or {}
    errors, t = validate_task(data, now(), partial=True)
    if "deadline" in errors and data.get("deadline") and parse(data["deadline"]) == parse(task["deadline"]):
        errors.pop("deadline")   # keeping an existing past deadline is allowed when editing other fields
        t["deadline"] = task["deadline"]
    if errors:
        return error("Please correct the highlighted fields.", 400, fields=errors)
    if t:
        sets = ", ".join(f"{k} = ?" for k in t)
        db.execute(f"UPDATE tasks SET {sets} WHERE task_id = ?", tuple(t.values()) + (task_id,))
    plan = _after_change(db)
    db.commit()
    return jsonify({"task": db.query("SELECT * FROM tasks WHERE task_id = ?", (task_id,), one=True),
                    "warning": _weight_warning(db, task["course_id"]), "plan": plan})


@bp.delete("/tasks/<int:task_id>")
@auth_required("student")
def delete_task(task_id):
    db = get_db()
    if not _own_task(db, task_id):
        return error("Task not found.", 404)
    db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    _after_change(db)
    db.commit()
    return jsonify({"message": "Task deleted."})


# ---------- availability (FR-04, FR-09, FR-10) ----------
@bp.get("/availability")
@auth_required("student")
def get_availability():
    db, uid = get_db(), g.user["user_id"]
    return jsonify({
        "blocks": db.query("SELECT * FROM availability_blocks WHERE student_id = ? ORDER BY day_of_week, start_time", (uid,)),
        "busy_events": db.query("SELECT * FROM busy_events WHERE student_id = ? ORDER BY start_at", (uid,)),
        "settings": db.query("SELECT daily_study_limit, session_length, reminder_lead_time, quiet_hours_start, quiet_hours_end "
                             "FROM students WHERE user_id = ?", (uid,), one=True),
    })


@bp.put("/availability")
@auth_required("student")
def save_availability():
    """Replace the weekly free-time blocks and save the study settings."""
    data, db, uid = request.get_json(silent=True) or {}, get_db(), g.user["user_id"]
    blocks, errors = [], {}
    for i, b in enumerate(data.get("blocks", [])):
        try:
            day, st, en = int(b["day_of_week"]), parse_time(b["start_time"]), parse_time(b["end_time"])
            if not 0 <= day <= 6 or en <= st:
                raise ValueError
            blocks.append((day, st.strftime("%H:%M:%S"), en.strftime("%H:%M:%S")))
        except (KeyError, TypeError, ValueError):
            errors[f"blocks[{i}]"] = "Each block needs a day and an end time after the start time."
    s = data.get("settings") or {}
    checks = (("daily_study_limit", 0.5, 12, float), ("session_length", 25, 120, int), ("reminder_lead_time", 5, 60, int))
    clean = {}
    for key, lo, hi, cast in checks:
        if key in s:
            try:
                v = cast(s[key])
                if not lo <= v <= hi:
                    raise ValueError
                clean[key] = v
            except (TypeError, ValueError):
                errors[key] = f"Must be between {lo:g} and {hi:g}"
    for key in ("quiet_hours_start", "quiet_hours_end"):
        if key in s:
            clean[key] = parse_time(s[key]).strftime("%H:%M:%S") if s[key] else None
    if errors:
        return error("Please correct the highlighted fields.", 400, fields=errors)
    if "blocks" in data:
        db.execute("DELETE FROM availability_blocks WHERE student_id = ?", (uid,))
        for day, st, en in blocks:
            db.execute("INSERT INTO availability_blocks (student_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
                       (uid, day, st, en))
    if clean:
        db.execute(f"UPDATE students SET {', '.join(k + ' = ?' for k in clean)} WHERE user_id = ?", tuple(clean.values()) + (uid,))
    plan = _after_change(db) if blocks else None
    db.commit()
    return jsonify({"message": "Availability saved.", "plan": plan})


@bp.post("/busy-events")
@auth_required("student")
def add_busy_event():
    data, db = request.get_json(silent=True) or {}, get_db()
    try:
        st, en = parse(data["start_at"]), parse(data["end_at"])
        title = (data.get("title") or "Busy").strip()[:100]
        if en <= st:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return error("Enter a start and an end time after it.", 400)
    eid = db.execute("INSERT INTO busy_events (student_id, title, start_at, end_at) VALUES (?, ?, ?, ?)",
                     (g.user["user_id"], title, fmt(st), fmt(en)))
    plan = _after_change(db)
    db.commit()
    return jsonify({"event_id": eid, "plan": plan}), 201


@bp.delete("/busy-events/<int:event_id>")
@auth_required("student")
def delete_busy_event(event_id):
    db = get_db()
    db.execute("DELETE FROM busy_events WHERE event_id = ? AND student_id = ?", (event_id, g.user["user_id"]))
    _after_change(db)
    db.commit()
    return jsonify({"message": "Busy event deleted."})
