"""Account and access helpers (subsystem S2): password hashing, tokens and role checks."""
import datetime as dt
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from .db import get_db

# NFR-07: Argon2id when argon2-cffi is installed, otherwise Werkzeug's salted scrypt hash.
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError

    _ph = PasswordHasher()

    def hash_password(password):
        return _ph.hash(password)

    def check_password(stored_hash, password):
        try:
            return _ph.verify(stored_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            from werkzeug.security import check_password_hash
            return (not stored_hash.startswith("$argon2")) and check_password_hash(stored_hash, password)
        except Exception:
            return False

    HASH_METHOD = "argon2id"
except ImportError:  # pragma: no cover - depends on installed packages
    from werkzeug.security import check_password_hash, generate_password_hash

    def hash_password(password):
        return generate_password_hash(password, method="scrypt")

    def check_password(stored_hash, password):
        if stored_hash.startswith("$argon2"):
            return False
        return check_password_hash(stored_hash, password)

    HASH_METHOD = "scrypt"


def make_token(user, purpose="access", minutes=None):
    minutes = minutes or current_app.config["TOKEN_MINUTES"]
    payload = {
        "sub": str(user["user_id"]), "role": user["role"], "purpose": purpose,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def read_token(token, purpose="access"):
    data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    if data.get("purpose") != purpose:
        raise jwt.InvalidTokenError("wrong token purpose")
    return data


def error(message, status, **extra):
    body = {"error": message}
    body.update(extra)
    return jsonify(body), status


def auth_required(*roles):
    """Decorator: the request must carry a valid token; optionally one of the given roles (NFR-10)."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return error("Please log in.", 401)
            try:
                data = read_token(header[7:])
            except jwt.ExpiredSignatureError:
                return error("Your session has expired. Please log in again.", 401)
            except jwt.InvalidTokenError:
                return error("Please log in.", 401)
            user = get_db().query("SELECT * FROM users WHERE user_id = ?", (int(data["sub"]),), one=True)
            if not user or user["status"] == "deactivated":
                return error("This account is not active.", 403)
            if roles and user["role"] not in roles:
                return error("Access denied.", 403)
            g.user = user
            return view(*args, **kwargs)

        return wrapper

    return decorator


def log_event(db, level, message, user_id=None):
    db.execute("INSERT INTO system_logs (user_id, level, message, created_at) VALUES (?, ?, ?, ?)",
               (user_id, level, message[:500], dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
