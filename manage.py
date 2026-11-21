"""Command-line helper.

  python manage.py init-db     create all tables (MySQL or SQLite, from DATABASE_URL)
  python manage.py seed        load demo accounts and data for the presentation
  python manage.py reset-demo  delete the local SQLite demo database, then init-db and seed
  python manage.py run         start the web server on http://127.0.0.1:5000
  python manage.py run-jobs    run the background jobs once (reminders, missed sessions, alerts)
"""
import os
import sys

from app import create_app
from app.config import Config
from app.db import BASE_DIR, Database, init_schema


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    url = Config.DATABASE_URL
    if cmd == "init-db":
        init_schema(url)
        print("Tables created.")
    elif cmd == "seed":
        from database.seed import seed
        print(seed(url))
    elif cmd == "reset-demo":
        if not url.startswith("sqlite"):
            sys.exit("reset-demo only works with the local SQLite database.")
        path = url.replace("sqlite:///", "", 1)
        path = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
        if os.path.exists(path):
            os.remove(path)
        init_schema(url)
        from database.seed import seed
        print(seed(url))
    elif cmd == "run":
        app = create_app()
        app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
    elif cmd == "run-jobs":
        from app.jobs import run_all
        from app.timeutil import now
        db = Database(url)
        print(run_all(db, now()))
        db.commit()
        db.close()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
