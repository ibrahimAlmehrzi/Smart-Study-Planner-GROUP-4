# Smart Study Planner – Group 4

A web application that turns a student's courses, deadlines and free time into a weekly study timetable, and keeps that timetable up to date when plans change.

SWE 401 Software Engineering · Abu Dhabi University · Fall 2026 · Instructor: Dr. Murad Al-Rajab

## Team members

| Name | ID | Role in the project | Main parts of the code |
|---|---|---|---|
| Ibrahim Almehrzi | 1090640 | Group leader, back end | `app/planning/`, `app/plan_service.py`, `app/routes/`, `app/jobs.py`, `app/notifications.py` |
| Yousef Alzaabi | 1090314 | Database (MySQL) | `database/`, `app/db.py`, `app/progress.py` |
| Ali Alneyadi | 1057663 | Front end, testing, deployment | `app/static/`, `tests/`, `docs/` |

## Problem

University students often manage several courses with deadlines, exams and part-time commitments at the same time. Most students plan by hand or in a basic calendar, which does not tell them what to study first or how to recover when a session is missed. As a result, work piles up before deadlines and exam revision starts too late.

## Key features

- **Accounts and roles**: student, academic advisor and administrator accounts. Passwords are hashed and an account locks for 15 minutes after 5 failed logins. Password reset links can be used once and expire after 30 minutes.
- **Courses and tasks**: add courses and tasks (assignment, exam, quiz, project, reading) with deadline, grade weight, difficulty and estimated hours. Every field is checked, and a warning appears if a course's weights add up to more than 100%.
- **Free time**: weekly availability blocks, one-off busy events, a daily study limit, session length and quiet hours.
- **Priority ranking**: `score = grade weight × difficulty × 1 / (days left + 1)`, with a short reason shown for each task (for example "due in 3 days · 15% of grade · hard").
- **Automatic weekly plan**: study sessions of 25 to 120 minutes are placed inside free time, before each deadline and within the daily limit. Review sessions are added 7, 3 and 1 day before every exam. Tasks that cannot fit are flagged as *at risk*.
- **Session tracking and rescheduling**: sessions can be marked completed, partly completed or missed. A missed session moves to the next free slot, or is split into two parts, or the student is told there is no time left. Locked sessions are never moved, and a session with no status 2 hours after it ends counts as missed.
- **Reminders and alerts**: session reminders, deadline alerts 3 days and 1 day before, and quiet hours.
- **Progress dashboard**: weekly completion rate, study streak, overdue tasks, a 5-week history chart and a per-course breakdown.
- **Sharing with an advisor**: a student can share a summary (completion rate, streak, overdue tasks) with an advisor and turn it off at any time. An advisor cannot see a student who is not sharing.
- **Administration**: search and filter users, deactivate or reactivate accounts, view usage figures and the system log.
- **Export**: weekly plan as an `.ics` calendar file (Google Calendar, Outlook) and personal data as CSV.

## Technologies

| Layer | Technology |
|---|---|
| Front end | HTML5, CSS3, JavaScript (no framework), Fetch API |
| Back end | Python 3, Flask 3 (REST API using blueprints) |
| Authentication | JSON Web Tokens (PyJWT, HS256), Argon2id password hashing (argon2-cffi) |
| Database | MySQL 8 in production through PyMySQL; SQLite for local runs and automated tests |
| Testing | Python `unittest` and the Flask test client |
| Tools | Git and GitHub, Visual Studio Code, MySQL Workbench |

## Project structure

```
Smart-Study-Planner-GROUP-4/
├── app/
│   ├── __init__.py          # create_app(): registers routes, serves the web pages
│   ├── config.py            # settings (read from environment variables or .env)
│   ├── db.py                # database access for MySQL and SQLite
│   ├── security.py          # password hashing, tokens, role checks
│   ├── planning/            # priority engine, schedule generator, rescheduling (no database code)
│   ├── plan_service.py      # connects the planning engine to the database
│   ├── progress.py          # weekly figures, streak, advisor summary
│   ├── notifications.py     # reminders, deadline alerts, quiet hours
│   ├── jobs.py              # background jobs (missed sessions, alerts, weekly summary)
│   ├── routes/              # REST API: auth, courses, plans, progress, admin
│   └── static/              # web pages, style sheet and JavaScript
├── database/
│   ├── schema_mysql.sql     # MySQL 8 schema (14 tables, matches the Phase 4 design)
│   ├── schema_sqlite.sql    # same tables for SQLite
│   └── seed.py              # demo accounts and data
├── tests/                   # 32 automated tests
├── docs/                    # test log and screenshots
├── manage.py                # command-line helper
├── requirements.txt
└── .env.example
```

## Prerequisites

- Python 3.10 or newer (tested with Python 3.13) and `pip`
- Git
- A web browser (Chrome, Edge or Firefox)
- MySQL 8.0.16 or newer, only if you want to run on MySQL. Without MySQL, the app uses a local SQLite file.

## Installation

```bash
git clone https://github.com/ibrahimAlmehrzi/Smart-Study-Planner-GROUP-4.git
cd Smart-Study-Planner-GROUP-4

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and edit the values:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

| Setting | What it does | Default |
|---|---|---|
| `SECRET_KEY` | Signs login tokens. Use a long random value. | development key |
| `DATABASE_URL` | `sqlite:///instance/planner.db` or `mysql://user:password@host:3306/smart_study_planner` | SQLite file |
| `TOKEN_MINUTES` | How long a login stays valid | 30 |
| `ENABLE_JOBS` | `1` runs reminders and the missed-session check every minute, `0` turns them off | 1 |
| `HOST`, `PORT` | Address of the web server | 127.0.0.1, 5000 |

### Using MySQL

1. Create the database and a user in MySQL Workbench or the MySQL shell:
   ```sql
   CREATE DATABASE smart_study_planner;
   CREATE USER 'planner_user'@'localhost' IDENTIFIED BY 'your_password';
   GRANT ALL PRIVILEGES ON smart_study_planner.* TO 'planner_user'@'localhost';
   ```
2. Set `DATABASE_URL=mysql://planner_user:your_password@localhost:3306/smart_study_planner` in `.env`.
3. Create the tables and load the demo data:
   ```bash
   python manage.py init-db
   python manage.py seed
   ```

## How to run

Quick start with SQLite and the demo data:

```bash
python manage.py reset-demo     # creates instance/planner.db and loads the demo data
python manage.py run            # starts the server
```

Open **http://127.0.0.1:5000** and log in with one of the demo accounts. The password for all of them is `Demo@1234`.

| Role | Email | What it shows |
|---|---|---|
| Student | aisha@demo.adu.ac.ae | 4 courses, 7 open tasks, a generated plan with exam reviews, 4 weeks of history, sharing with the advisor |
| Student | omar@demo.adu.ac.ae | Shared with the advisor and then turned sharing off |
| Advisor | h.ali@demo.adu.ac.ae | Sees Aisha's summary; access to Omar is refused |
| Admin | admin@demo.adu.ac.ae | User management, usage figures, system log |

Demo dates are set relative to the day the data is loaded, so run `python manage.py reset-demo` again before a presentation.

Other commands:

```bash
python manage.py init-db     # create the tables only
python manage.py seed        # load demo data into an empty database
python manage.py run-jobs    # run the background jobs once
```

## How to test

```bash
python -m unittest -v
```

The tests use a temporary SQLite database, so they do not change your data. Expected result: `Ran 32 tests ... OK`.

| File | What it checks |
|---|---|
| `tests/test_priority.py` | Priority formula, overdue tasks, invalid input, ranking and tie-break, explanation text (TC-01 to TC-05) |
| `tests/test_scheduler.py` | Free time, placing sessions within limits and deadlines, exam reviews, at-risk tasks, rescheduling (move, split, no slot), 2-hour timeout (TC-06 to TC-15) |
| `tests/test_api.py` | Register and login, account lockout, single-use reset link, task validation, plan generation, missed and locked sessions, calendar export, advisor access with and without consent, role checks, admin deactivation, password hashing, data export and account deletion (TC-16 to TC-32) |

To see how much of the planning code the tests run (NFR-17 asks for at least 70%):

```bash
python tests/measure_coverage.py
```

The latest test log, coverage result and screenshots of the running system are in `docs/`.

## Known limitations of this prototype

- New accounts are marked as email-verified straight away. Sending the verification email needs an SMTP account.
- Reminders and alerts go through a notification gateway that writes to the server log instead of sending real emails or push notifications. Connecting SMTP or Firebase Cloud Messaging only requires changing `NotificationGateway.send` in `app/notifications.py`.
- Background jobs run in a simple thread inside the web process. A production server would use a separate scheduler (for example cron or APScheduler).
- `python manage.py run` uses Flask's development server. For deployment, use a WSGI server such as Gunicorn or Waitress behind HTTPS.
