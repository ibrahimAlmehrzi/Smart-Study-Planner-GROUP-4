"""Demo data for the live presentation. Dates are relative to today, so the demo works on any day.

Accounts (password for all: Demo@1234)
  student  aisha@demo.adu.ac.ae    – four courses, tasks, free time, past study history, shares with the advisor
  student  omar@demo.adu.ac.ae     – shared with the advisor, then turned off (shows "access denied")
  advisor  h.ali@demo.adu.ac.ae
  admin    admin@demo.adu.ac.ae
"""
import datetime as dt
import random

from app.db import Database
from app.security import hash_password
from app.timeutil import fmt, now

PASSWORD = "Demo@1234"


def _user(db, name, email, role, created):
    uid = db.execute("INSERT INTO users (full_name, email, password_hash, role, status, email_verified, created_at) "
                     "VALUES (?, ?, ?, ?, 'active', 1, ?)", (name, email, hash_password(PASSWORD), role, fmt(created)))
    if role == "student":
        db.execute("INSERT INTO students (user_id, quiet_hours_start, quiet_hours_end) VALUES (?, '23:00:00', '07:00:00')", (uid,))
    elif role == "advisor":
        db.execute("INSERT INTO advisors (user_id, department) VALUES (?, 'Computer Science')", (uid,))
    else:
        db.execute("INSERT INTO administrators (user_id, staff_id) VALUES (?, 'ADM-001')", (uid,))
    return uid


def seed(url, today=None):
    random.seed(4)
    t = today or now()
    day0 = t.replace(hour=0, minute=0, second=0, microsecond=0)
    db = Database(url)
    if db.query("SELECT 1 AS x FROM users LIMIT 1", one=True):
        db.close()
        return "Database already has data; seed skipped."

    created = t - dt.timedelta(days=60)
    aisha = _user(db, "Aisha Khalid", "aisha@demo.adu.ac.ae", "student", created)
    omar = _user(db, "Omar Saeed", "omar@demo.adu.ac.ae", "student", created)
    advisor = _user(db, "Dr. Hassan Ali", "h.ali@demo.adu.ac.ae", "advisor", created)
    _user(db, "System Admin", "admin@demo.adu.ac.ae", "admin", created)

    # Weekly free time (Mon=0 ... Sun=6)
    blocks = {0: [("16:00", "20:00")], 1: [("09:00", "11:00"), ("16:00", "21:00")], 2: [("16:00", "20:00")],
              3: [("09:00", "11:00"), ("17:00", "21:00")], 4: [("14:00", "18:00")], 5: [("10:00", "14:00")],
              6: [("15:00", "19:00")]}
    for sid in (aisha, omar):
        for d, spans in blocks.items():
            for a, b in spans:
                db.execute("INSERT INTO availability_blocks (student_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
                           (sid, d, a + ":00", b + ":00"))
    db.execute("INSERT INTO busy_events (student_id, title, start_at, end_at) VALUES (?, 'Family event', ?, ?)",
               (aisha, fmt(day0 + dt.timedelta(days=5, hours=15)), fmt(day0 + dt.timedelta(days=5, hours=18))))

    courses = [("SWE 401", "Software Engineering"), ("CSC 305", "Database Systems"),
               ("MTH 211", "Linear Algebra"), ("ENG 210", "Technical Writing")]
    cid = {}
    for code, name in courses:
        cid[code] = db.execute("INSERT INTO courses (student_id, course_code, course_name, credit_hours) VALUES (?, ?, ?, 3)",
                               (aisha, code, name))
    # (course, title, type, days from today, hour, weight, difficulty, hours)
    tasks = [
        ("SWE 401", "Phase 5 implementation", "project", 6, 23, 20, 3, 8),
        ("SWE 401", "Final presentation", "assignment", 9, 10, 10, 2, 3),
        ("CSC 305", "ER diagram assignment", "assignment", 3, 23, 15, 3, 4),
        ("CSC 305", "Midterm exam", "exam", 10, 10, 30, 4, 6),
        ("MTH 211", "Assignment 3", "assignment", 4, 23, 10, 4, 5),
        ("MTH 211", "Quiz 4", "quiz", 7, 12, 5, 2, 1.5),
        ("ENG 210", "Report draft reading", "reading", 5, 18, 5, 1, 2),
    ]
    for code, title, ttype, days, hour, w, d, h in tasks:
        db.execute("INSERT INTO tasks (course_id, title, task_type, deadline, grade_weight, difficulty, estimated_hours) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)", (cid[code], title, ttype, fmt(day0 + dt.timedelta(days=days, hours=hour)), w, d, h))

    # Past study history over the last 4 weeks (for the dashboard and advisor charts).
    done_task = db.execute("INSERT INTO tasks (course_id, title, task_type, deadline, grade_weight, difficulty, estimated_hours, status) "
                           "VALUES (?, 'Weekly lab work', 'assignment', ?, 10, 2, 30, 'done')",
                           (cid["SWE 401"], fmt(day0 - dt.timedelta(hours=1))))
    db.execute("INSERT INTO tasks (course_id, title, task_type, deadline, grade_weight, difficulty, estimated_hours) "
               "VALUES (?, 'Lab report 2', 'assignment', ?, 5, 2, 2)", (cid["ENG 210"], fmt(day0 - dt.timedelta(days=1, hours=1))))
    for back in range(28, 0, -1):
        day = day0 - dt.timedelta(days=back)
        if day.weekday() in (2, 5) and back > 3:
            continue
        status = "completed" if random.random() < 0.82 or back <= 6 else random.choice(["missed", "partly_completed"])
        st = day + dt.timedelta(hours=17)
        db.execute("INSERT INTO study_sessions (task_id, session_type, planned_start, planned_end, status) "
                   "VALUES (?, 'study', ?, ?, ?)", (done_task, fmt(st), fmt(st + dt.timedelta(minutes=50)), status))

    # Omar shared with the advisor and then turned sharing off.
    db.execute("INSERT INTO sharing_consents (student_id, advisor_id, is_active, granted_at, revoked_at) VALUES (?, ?, 0, ?, ?)",
               (omar, advisor, fmt(t - dt.timedelta(days=30)), fmt(t - dt.timedelta(days=2))))
    db.execute("INSERT INTO sharing_consents (student_id, advisor_id, is_active, granted_at) VALUES (?, ?, 1, ?)",
               (aisha, advisor, fmt(t - dt.timedelta(days=20))))
    db.commit()

    from app.plan_service import regenerate_plan
    result = regenerate_plan(db, aisha, t)
    db.commit()
    db.close()
    return f"Demo data created. Plan for Aisha: {result.get('sessions_created')} sessions."
