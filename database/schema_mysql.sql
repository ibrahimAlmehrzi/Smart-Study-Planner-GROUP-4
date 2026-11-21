-- Smart Study Planner – MySQL 8 schema (Group 4). Matches the Phase 4 data design.
-- Requires MySQL 8.0.16 or later (CHECK constraints are enforced).

CREATE DATABASE IF NOT EXISTS smart_study_planner;
USE smart_study_planner;

CREATE TABLE users (
    user_id            INT AUTO_INCREMENT PRIMARY KEY,
    full_name          VARCHAR(100) NOT NULL,
    email              VARCHAR(150) NOT NULL UNIQUE,
    password_hash      VARCHAR(255) NOT NULL,
    role               ENUM('student','advisor','admin') NOT NULL,
    status             ENUM('active','locked','deactivated') NOT NULL DEFAULT 'active',
    email_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_count TINYINT NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until       DATETIME NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE students (
    user_id            INT PRIMARY KEY,
    time_zone          VARCHAR(50) NOT NULL DEFAULT 'Asia/Dubai',
    daily_study_limit  DECIMAL(3,1) NOT NULL DEFAULT 4.0 CHECK (daily_study_limit BETWEEN 0.5 AND 12),
    session_length     SMALLINT NOT NULL DEFAULT 50 CHECK (session_length BETWEEN 25 AND 120),
    reminder_lead_time SMALLINT NOT NULL DEFAULT 15 CHECK (reminder_lead_time BETWEEN 5 AND 60),
    quiet_hours_start  TIME NULL,
    quiet_hours_end    TIME NULL,
    current_streak     INT NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE advisors (
    user_id    INT PRIMARY KEY,
    department VARCHAR(100) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE administrators (
    user_id  INT PRIMARY KEY,
    staff_id VARCHAR(20) NOT NULL UNIQUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE courses (
    course_id    INT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    course_code  VARCHAR(20) NOT NULL,
    course_name  VARCHAR(100) NOT NULL,
    credit_hours TINYINT NOT NULL DEFAULT 3 CHECK (credit_hours BETWEEN 0 AND 6),
    UNIQUE (student_id, course_code),
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE
);

CREATE TABLE tasks (
    task_id         INT AUTO_INCREMENT PRIMARY KEY,
    course_id       INT NOT NULL,
    title           VARCHAR(150) NOT NULL,
    task_type       ENUM('assignment','exam','quiz','project','reading') NOT NULL,
    deadline        DATETIME NOT NULL,
    grade_weight    DECIMAL(5,2) NOT NULL CHECK (grade_weight BETWEEN 0 AND 100),
    difficulty      TINYINT NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
    estimated_hours DECIMAL(4,1) NOT NULL CHECK (estimated_hours > 0),
    status          ENUM('pending','in_progress','done') NOT NULL DEFAULT 'pending',
    priority_score  DECIMAL(8,2) NULL,
    at_risk         BOOLEAN NOT NULL DEFAULT FALSE,
    INDEX idx_tasks_deadline (deadline),
    FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE
);

CREATE TABLE availability_blocks (
    block_id    INT AUTO_INCREMENT PRIMARY KEY,
    student_id  INT NOT NULL,
    day_of_week TINYINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time  TIME NOT NULL,
    end_time    TIME NOT NULL,
    CHECK (end_time > start_time),
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE
);

CREATE TABLE busy_events (
    event_id   INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    title      VARCHAR(100) NOT NULL,
    start_at   DATETIME NOT NULL,
    end_at     DATETIME NOT NULL,
    CHECK (end_at > start_at),
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE
);

CREATE TABLE study_plans (
    plan_id      INT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    week_start   DATE NOT NULL,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, week_start),
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE
);

CREATE TABLE study_sessions (
    session_id         INT AUTO_INCREMENT PRIMARY KEY,
    task_id            INT NOT NULL,
    plan_id            INT NULL,
    session_type       ENUM('study','review') NOT NULL DEFAULT 'study',
    review_offset_days TINYINT NULL,
    planned_start      DATETIME NOT NULL,
    planned_end        DATETIME NOT NULL,
    status             ENUM('planned','completed','partly_completed','missed','rescheduled') NOT NULL DEFAULT 'planned',
    is_locked          BOOLEAN NOT NULL DEFAULT FALSE,
    reschedule_count   TINYINT NOT NULL DEFAULT 0,
    CHECK (planned_end > planned_start),
    CHECK ((session_type = 'study' AND review_offset_days IS NULL)
        OR (session_type = 'review' AND review_offset_days IN (7, 3, 1))),
    INDEX idx_sessions_start (planned_start),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES study_plans(plan_id) ON DELETE SET NULL
);

CREATE TABLE notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id      INT NOT NULL,
    session_id      INT NULL,
    task_id         INT NULL,
    type            ENUM('reminder','deadline_alert','update','weekly_summary') NOT NULL,
    message         VARCHAR(255) NOT NULL,
    scheduled_for   DATETIME NOT NULL,
    sent_at         DATETIME NULL,
    delivery_status ENUM('pending','sent','failed') NOT NULL DEFAULT 'pending',
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES study_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE sharing_consents (
    consent_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    advisor_id INT NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME NULL,
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE,
    FOREIGN KEY (advisor_id) REFERENCES advisors(user_id) ON DELETE CASCADE
);

CREATE TABLE progress_summaries (
    summary_id         INT AUTO_INCREMENT PRIMARY KEY,
    student_id         INT NOT NULL,
    week_start         DATE NOT NULL,
    planned_sessions   SMALLINT NOT NULL DEFAULT 0,
    completed_sessions SMALLINT NOT NULL DEFAULT 0,
    completion_rate    DECIMAL(5,2) NOT NULL DEFAULT 0 CHECK (completion_rate BETWEEN 0 AND 100),
    streak             INT NOT NULL DEFAULT 0,
    overdue_tasks      SMALLINT NOT NULL DEFAULT 0,
    UNIQUE (student_id, week_start),
    FOREIGN KEY (student_id) REFERENCES students(user_id) ON DELETE CASCADE
);

CREATE TABLE system_logs (
    log_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NULL,
    level      ENUM('INFO','WARN','ERROR') NOT NULL,
    message    VARCHAR(500) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);
