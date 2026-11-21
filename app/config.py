"""Application settings. Values can be overridden with environment variables (see .env.example)."""
import os


def _load_env_file():
    """Read KEY=value lines from a .env file in the project folder (no extra package needed).
    Values already set in the environment win."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-key-change-me-in-production")
    # MySQL example: mysql://planner_user:password@localhost:3306/smart_study_planner
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/planner.db")
    TOKEN_MINUTES = int(os.environ.get("TOKEN_MINUTES", "30"))       # NFR-09
    MAX_FAILED_LOGINS = 5                                            # FR-02
    LOCK_MINUTES = 15                                                # FR-02
    UNMARKED_TIMEOUT_HOURS = 2                                       # FR-18
    RESET_TOKEN_MINUTES = 30                                         # FR-03
    ENABLE_JOBS = os.environ.get("ENABLE_JOBS", "1") == "1"          # background jobs thread
    JOB_INTERVAL_SECONDS = int(os.environ.get("JOB_INTERVAL_SECONDS", "60"))
    TESTING = False
