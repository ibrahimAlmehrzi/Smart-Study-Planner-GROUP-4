"""Notification subsystem (S5): NotificationController and NotificationGateway (UC-10, FR-21, FR-22, FR-24)."""
import datetime as dt
import logging

from .timeutil import fmt, parse, parse_time

log = logging.getLogger("notifications")


class NotificationGateway:
    """Boundary to the external email / push service.

    The prototype writes each message to the server log instead of calling a real provider.
    To go live, replace send() with an SMTP or Firebase Cloud Messaging call; nothing else changes.
    """

    sent = []  # kept in memory so tests and the demo can show what was delivered

    @classmethod
    def send(cls, email, message):
        cls.sent.append((email, message))
        log.info("NOTIFY %s: %s", email, message)
        return "sent"


def queue(db, student_id, ntype, message, when, session_id=None, task_id=None):
    return db.execute(
        "INSERT INTO notifications (student_id, session_id, task_id, type, message, scheduled_for, delivery_status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (student_id, session_id, task_id, ntype, message, fmt(when)))


def cancel_session_reminders(db, session_id):
    db.execute("DELETE FROM notifications WHERE session_id = ? AND type = 'reminder' AND delivery_status = 'pending'",
               (session_id,))


def schedule_reminder(db, student, session, course_code, task_title):
    """FR-21: one reminder before each session, using the student's chosen lead time."""
    cancel_session_reminders(db, session["session_id"])
    start = parse(session["planned_start"])
    when = start - dt.timedelta(minutes=int(student["reminder_lead_time"]))
    label = "Review" if session.get("session_type") == "review" else "Study session"
    msg = f"{label}: {course_code} {task_title} starts at {start:%H:%M}."
    queue(db, student["user_id"], "reminder", msg, when, session_id=session["session_id"])


def _in_quiet_hours(student, moment):
    if not student.get("quiet_hours_start") or not student.get("quiet_hours_end"):
        return False
    qs, qe, t = parse_time(student["quiet_hours_start"]), parse_time(student["quiet_hours_end"]), moment.time()
    return (qs <= t or t < qe) if qs > qe else (qs <= t < qe)


def deliver_due(db, now):
    """Send every pending notification that is due, except during the student's quiet hours (FR-22)."""
    due = db.query(
        "SELECT n.*, u.email, s.quiet_hours_start, s.quiet_hours_end FROM notifications n "
        "JOIN users u ON u.user_id = n.student_id JOIN students s ON s.user_id = n.student_id "
        "WHERE n.delivery_status = 'pending' AND n.scheduled_for <= ?", (fmt(now),))
    count = 0
    for n in due:
        if _in_quiet_hours(n, now):
            continue
        status = NotificationGateway.send(n["email"], n["message"])
        db.execute("UPDATE notifications SET delivery_status = ?, sent_at = ? WHERE notification_id = ?",
                   (status, fmt(now), n["notification_id"]))
        count += 1
    return count


def create_deadline_alerts(db, now):
    """FR-22: alerts 3 days and 1 day before each open task's deadline (created once each)."""
    created = 0
    for days in (3, 1):
        window_end = now + dt.timedelta(days=days)
        rows = db.query(
            "SELECT t.task_id, t.title, t.deadline, c.course_code, c.student_id FROM tasks t "
            "JOIN courses c ON c.course_id = t.course_id WHERE t.status <> 'done' AND t.deadline > ? AND t.deadline <= ?",
            (fmt(now), fmt(window_end)))
        for r in rows:
            msg = f"Reminder: {r['course_code']} {r['title']} is due in {days} day{'s' if days > 1 else ''}."
            exists = db.query("SELECT 1 AS x FROM notifications WHERE task_id = ? AND type = 'deadline_alert' AND message = ?",
                              (r["task_id"], msg), one=True)
            if not exists:
                queue(db, r["student_id"], "deadline_alert", msg, now, task_id=r["task_id"])
                created += 1
    return created
