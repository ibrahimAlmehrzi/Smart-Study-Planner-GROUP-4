"""Smart Study Planner – Flask application factory (Tier 2 of the Phase 4 architecture)."""
import logging
import os

from flask import Flask, jsonify, send_from_directory

from .config import Config
from .db import close_db


def create_app(overrides=None):
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from .routes import admin, auth, courses, plans, progress
    for module in (auth, courses, plans, progress, admin):
        app.register_blueprint(module.bp)
    app.teardown_appcontext(close_db)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"error": "Something went wrong on our side. Please try again."}), 500

    if app.config["ENABLE_JOBS"] and not app.config["TESTING"] and os.environ.get("WERKZEUG_RUN_MAIN") != "false":
        from .jobs import start_background_jobs
        start_background_jobs(app)
    return app
