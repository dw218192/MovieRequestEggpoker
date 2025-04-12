import os
import logging
import atexit

from flask import Flask
from .extensions import g_db, g_limiter
from .routes import main_bp

def init_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("MOVIE_REQUEST_SERVER_SECRET")
    app.register_blueprint(main_bp)

    if os.getenv("MOVIE_REQUEST_SERVER_CLEAR_DB_ON_STARTUP", "false").lower() == "true":
        g_db.drop()
    g_db.connect()
    g_limiter.init_app(app)
    atexit.register(lambda: g_db.close())
    return app

g_app = init_app()


logger = logging.getLogger(__package__)

if __name__ == "__main__":
    g_app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.getenv("MOVIE_REQUEST_SERVER_PORT", 5000)),
    )
