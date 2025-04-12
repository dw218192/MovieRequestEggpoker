import os
from pathlib import Path

import app.db as db
import app.jellyfin as jellyfin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def limiter_key_func():
    user = jellyfin.get_current_user()
    if user is None:
        return get_remote_address()
    return user["id"]

DB_FILE = os.getenv(
    "MOVIE_REQUEST_SERVER_DB_PATH", str(Path(__file__).parent / "db.json")
)


g_db = db.JsonDatabase(DB_FILE)
g_limiter = Limiter(
    key_func=limiter_key_func,
    storage_uri=os.getenv("MOVIE_REQUEST_SERVER_RATE_LIMIT_STORAGE_URI", "memory://"),
)

