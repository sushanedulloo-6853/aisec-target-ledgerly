import logging

from flask import Flask, jsonify, send_from_directory

from ledgerly import worker
from ledgerly.config import settings
from ledgerly.db import close_db, connect, init_db
from ledgerly.llm import LLMNotConfigured

log = logging.getLogger("ledgerly")


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static")
    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = settings.MAX_UPLOAD_MB * 1024 * 1024
    if config:
        app.config.update(config)

    conn = connect()
    init_db(conn)
    conn.close()

    from ledgerly.api import books, categorizer, copilot, documents

    for module in (books, copilot, categorizer, documents):
        app.register_blueprint(module.bp)

    app.teardown_appcontext(close_db)
    worker.start_background_thread()

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(LLMNotConfigured)
    def llm_not_configured(exc):
        return jsonify(error="AI features are not configured: " + str(exc)), 503

    return app


app = None


def get_app() -> Flask:
    global app
    if app is None:
        app = create_app()
    return app
