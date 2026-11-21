-- Smart Study Planner – SQLite version of schema_mysql.sql, used for automated tests and quick demos.
-- Same tables, columns and constraints; ENUM columns become TEXT with CHECK (... IN ...).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name          TEXT NOT NULL,
    email              TEXT NOT NULL UNIQUE,
    password_hash      TEXT NOT NULL,
    role               TEXT NOT NULL CHECK (role IN ('student','advisor','admin')),
    status             TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','locked','deactivated')),
    email_verified     INTEGER NOT NULL DEFAULT 0,
    failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until       TEXT NULL,
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    user_id            INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    time_zone          TEXT NOT NULL DEFAULT 'Asia/Dubai',
    daily_study_limit  REAL NOT NULL DEFAULT 4.0 CHECK (daily_study_limit BETWEEN 0.5 AND 12),
    session_length     INTEGER NOT NULL DEFAULT 50 CHECK (session_length BETWEEN 25 AND 120),
    reminder_lead_time INTEGER NOT NULL DEFAULT 15 CHECK (reminder_lead_time BETWEEN 5 AND 60),
    quiet_hours_start  TEXT NULL,
    quiet_hours_end    TEXT NULL,
    current_streak     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS advisors (
    user_id    INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    department TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS administrators (
    user_id  INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    staff_id TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS courses (
    course_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    course_code  TEXT NOT NULL,
    course_name  TEXT NOT NULL,
    credit_hours INTEGER NOT NULL DEFAULT 3 CHECK (credit_hours BETWEEN 0 AND 6),
    UNIQUE (student_id, course_code)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id       INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    task_type       TEXT NOT NULL CHECK (task_type IN ('assignment','exam','quiz','project','reading')),
    deadline        TEXT NOT NULL,
    grade_weight    REAL NOT NULL CHECK (grade_weight BETWEEN 0 AND 100),
    difficulty      INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
    estimated_hours REAL NOT NULL CHECK (estimated_hours > 0),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_progress','done')),
    priority_score  REAL NULL,
    at_risk         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);

CREATE TABLE IF NOT EXISTS availability_blocks (
    block_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    CHECK (end_time > start_time)
);

CREATE TABLE IF NOT EXISTS busy_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    start_at   TEXT NOT NULL,
    end_at     TEXT NOT NULL,
    CHECK (end_at > start_at)
);

CREATE TABLE IF NOT EXISTS study_plans (
    plan_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    week_start   TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, week_start)
);

CREATE TABLE IF NOT EXISTS study_sessions (
    session_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            INTEGER NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    plan_id            INTEGER NULL REFERENCES study_plans(plan_id) ON DELETE SET NULL,
    session_type       TEXT NOT NULL DEFAULT 'study' CHECK (session_type IN ('study','review')),
    review_offset_days INTEGER NULL,
    planned_start      TEXT NOT NULL,
    planned_end        TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'planned'
                       CHECK (status IN ('planned','completed','partly_completed','missed','rescheduled')),
    is_locked          INTEGER NOT NULL DEFAULT 0,
    reschedule_count   INTEGER NOT NULL DEFAULT 0,
    CHECK (planned_end > planned_start),
    CHECK ((session_type = 'study' AND review_offset_days IS NULL)
        OR (session_type = 'review' AND review_offset_days IN (7, 3, 1)))
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON study_sessions(planned_start);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    session_id      INTEGER NULL REFERENCES study_sessions(session_id) ON DELETE CASCADE,
    task_id         INTEGER NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK (type IN ('reminder','deadline_alert','update','weekly_summary')),
    message         TEXT NOT NULL,
    scheduled_for   TEXT NOT NULL,
    sent_at         TEXT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (delivery_status IN ('pending','sent','failed'))
);

CREATE TABLE IF NOT EXISTS sharing_consents (
    consent_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    advisor_id INTEGER NOT NULL REFERENCES advisors(user_id) ON DELETE CASCADE,
    is_active  INTEGER NOT NULL DEFAULT 1,
    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT NULL,
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

CREATE TABLE IF NOT EXISTS progress_summaries (
    summary_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id         INTEGER NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    week_start         TEXT NOT NULL,
    planned_sessions   INTEGER NOT NULL DEFAULT 0,
    completed_sessions INTEGER NOT NULL DEFAULT 0,
    completion_rate    REAL NOT NULL DEFAULT 0 CHECK (completion_rate BETWEEN 0 AND 100),
    streak             INTEGER NOT NULL DEFAULT 0,
    overdue_tasks      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (student_id, week_start)
);

CREATE TABLE IF NOT EXISTS system_logs (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
    level      TEXT NOT NULL CHECK (level IN ('INFO','WARN','ERROR')),
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
