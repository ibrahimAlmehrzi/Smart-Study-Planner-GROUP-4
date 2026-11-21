"""Data access layer (subsystem S8).

One small wrapper over the Python DB-API so the same queries run on
MySQL 8 (production, through PyMySQL) and SQLite (local testing and demos).
Queries are written with "?" placeholders; they are converted to "%s" for MySQL.
"""
import datetime
import decimal
import os
import sqlite3
from urllib.parse import unquote, urlparse

from flask import current_app, g

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalise(value):
    """Return values in the same form for both databases (strings for dates and times)."""
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime.timedelta):  # MySQL TIME columns
        s = int(value.total_seconds())
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


class Database:
    def __init__(self, url):
        self.url = url
        if url.startswith("mysql"):
            import pymysql  # imported only when MySQL is used

            u = urlparse(url)
            self.kind = "mysql"
            self.conn = pymysql.connect(
                host=u.hostname or "localhost", port=u.port or 3306,
                user=unquote(u.username or ""), password=unquote(u.password or ""),
                database=u.path.lstrip("/"), charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor, autocommit=False,
            )
        else:
            self.kind = "sqlite"
            path = url.replace("sqlite:///", "", 1)
            if not os.path.isabs(path):
                path = os.path.join(BASE_DIR, path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.kind == "mysql" else sql

    def query(self, sql, params=(), one=False):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        rows = [{k: _normalise(v) for k, v in dict(r).items()} for r in cur.fetchall()]
        cur.close()
        if one:
            return rows[0] if rows else None
        return rows

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        last_id = cur.lastrowid
        cur.close()
        return last_id

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def get_db():
    if "db" not in g:
        g.db = Database(current_app.config["DATABASE_URL"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_schema(url):
    """Create all tables. Uses the MySQL or SQLite version of the schema."""
    db = Database(url)
    name = "schema_mysql.sql" if db.kind == "mysql" else "schema_sqlite.sql"
    with open(os.path.join(BASE_DIR, "database", name), encoding="utf-8") as f:
        script = f.read()
    if db.kind == "sqlite":
        db.conn.executescript(script)
    else:
        for statement in [s.strip() for s in script.split(";")]:
            lines = [ln for ln in statement.splitlines() if not ln.strip().startswith("--")]
            statement = "\n".join(lines).strip()
            if statement and not statement.upper().startswith(("CREATE DATABASE", "USE ")):
                db.execute(statement)
    db.commit()
    db.close()
