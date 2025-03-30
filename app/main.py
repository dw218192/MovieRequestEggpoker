import os
import functools
import logging
import inspect
from pathlib import Path
import atexit
from dataclasses import dataclass, field
import contextlib

from flask import Flask, request, session, redirect, render_template
import app.jackett as jackett
import app.jellyfin as jellyfin
import app.qbittorrent as qbittorrent
import app.db as db
import app.storage as storage

DB_FILE = os.getenv(
    "MOVIE_REQUEST_SERVER_DB_PATH", str(Path(__file__).parent / "db.json")
)

g_db = db.JsonDatabase(DB_FILE)


def init_app():
    app = Flask(__name__)
    if os.getenv("MOVIE_REQUEST_SERVER_CLEAR_DB_ON_STARTUP", "false").lower() == "true":
        g_db.drop()

    g_db.connect()
    atexit.register(lambda: g_db.close())
    return app


g_app = init_app()


@dataclass
class TranscientUserData:
    # a set of torrent titles that are being processed by /api/request (note this is not infohashes)
    # we store the title instead of infohashes because the latter is not available when this info is needed
    # this is not perfect, but in the worst case we accidentally block the ability to make request for a different torrent with the same title temporarily
    pending_requests: set[str] = field(default_factory=set)
    ref_count: int = 0


# a dict to store some transcient user data
# such as the torrent request status
g_transcient_user_data: dict[str, TranscientUserData] = {}


@contextlib.contextmanager
def transient_user_data(user_id: str):
    """Context manager to handle transient user data."""
    data = g_transcient_user_data.setdefault(user_id, TranscientUserData())

    try:
        data.ref_count += 1
        yield data
    finally:
        # Clean up the data after use
        data.ref_count -= 1
        if data.ref_count == 0:
            del g_transcient_user_data[user_id]


logger = logging.getLogger(__package__)


def login_required(f):
    if inspect.iscoroutinefunction(f):

        @functools.wraps(f)
        async def wrapper(*args, **kwargs):  # type:ignore
            user_session = jellyfin.get_current_user()
            if user_session is None:
                return "User not logged in", 401
            return await f(user=user_session, *args, **kwargs)

    else:

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user_session = jellyfin.get_current_user()
            if user_session is None:
                return "User not logged in", 401
            return f(user=user_session, *args, **kwargs)

    return wrapper


@g_app.route("/")
def index():
    if jellyfin.get_current_user() is None:
        return redirect("/login")
    return render_template("index.html")


@g_app.route("/login", methods=["GET"])
def login_page():
    if jellyfin.get_current_user():
        return redirect("/")
    return render_template("login.html")


@g_app.route("/fragment/search", methods=["POST"])
@login_required
async def search(user: jellyfin.JellyfinSession):
    body = request.get_json()
    if not isinstance(body, dict):
        logger.error(f"Invalid search request body: {body}")
        return "Invalid request body", 400

    search_type = body.get("type", None)
    query = body.get("query", None)

    if not query:
        return "Please provide a non-empty query", 400

    entries = await jackett.search(query)
    if entries is not None:
        for entry in entries:
            if title := entry.get("Title", None):
                if metadata := jackett.guess_metadata(title):
                    entry["GuessedMetadata"] = metadata
    else:
        entries = []
    with transient_user_data(user["id"]) as user_data:
        logger.info(f"User Data: {user_data}")
        return render_template(
            "fragments/search_res.html",
            query=query,
            entries=entries,
            user_data=user_data,
        )


@g_app.route("/fragment/qbittorrent/stats", methods=["GET"])
@login_required
async def qbittorrent_stats(user: jellyfin.JellyfinSession):
    requests = await g_db.get_requests(
        db.User(id=user["id"], username=user["username"])
    )
    entries = []
    if requests:
        entries = await qbittorrent.get_torrent_list(
            hashes=[req.torrent.infohash for req in requests],
        )
    with transient_user_data(user["id"]) as user_data:
        return render_template(
            "fragments/qbittorrent_stats.html", entries=entries, user_data=user_data
        )


@g_app.route("/fragment/user", methods=["GET"])
@login_required
async def user(user: jellyfin.JellyfinSession):
    return render_template("fragments/user.html", user=user)


@g_app.route("/api/login", methods=["POST"])
async def login():
    body = request.get_json()
    if not isinstance(body, dict):
        logger.error(f"Invalid login request body: {body}")
        return "Invalid request body", 400

    username = body.get("username", None)
    password = body.get("password", None)

    if username is None or password is None:
        logger.error(f"Missing username or password: {body}")
        return "Missing username or password", 400

    resp = await jellyfin.login(username, password)
    if not resp:
        return "Login failed", 401

    logger.info(f"Jellyfin User {username} logged in successfully")
    return "Login successful", 200


@g_app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@g_app.route("/api/request", methods=["POST"])
@login_required
async def request_torrent(user: jellyfin.JellyfinSession):
    body = request.get_json()
    if not isinstance(body, dict):
        logger.error(f"Invalid request body: {body}")
        return "Invalid request body", 400

    torrent_title = body.get("torrentTitle", None)
    torrent_link = body.get("torrentLink", None)
    torrent_size = body.get("torrentSize", None)
    if torrent_link is None or torrent_size is None:
        logger.error(f"Missing required params: {body}")
        return "Missing required params", 400

    logger.debug(f"User {user['username']} is about to request torrent: {torrent_link}")

    with transient_user_data(user["id"]) as user_data:
        # record the ongoing request in the transient user data
        if torrent_title is not None:
            user_data.pending_requests.add(torrent_title)

        torrent_hash = await qbittorrent.get_torrent_hash(torrent_link)
        if not torrent_hash:
            logger.error(f"Failed to get torrent hash for {torrent_link}")
            return "Failed to get torrent hash", 500

        if torrent_hash in user_data.pending_requests:
            logger.warning(
                f"User {user['username']} already has a pending request for torrent {torrent_hash}."
            )
            return "Torrent already requested", 400

        db_user = db.User(id=user["id"], username=user["username"])
        if await g_db.has_request(db_user, db.Torrent(torrent_hash)):
            logger.warning(
                f"User {user['username']} already has a DB request for torrent {torrent_hash}."
            )
            return "Torrent already requested", 400

        # add the torrent to qBittorrent
        best_path = storage.get_best_path(torrent_size)
        if best_path is None:
            logger.error(
                f"No disk can hold torrent {torrent_hash} with file size {torrent_size} bytes"
            )
            return "No disk can hold the file", 500

        logger.debug(f"add download job for {torrent_hash} to {best_path}")
        if not await qbittorrent.add_torrent(
            torrent_links=torrent_link,
            save_path=best_path,
            exist_ok=True,
        ):
            return "Failed to add torrent", 500

        # record the request in DB
        await g_db.make_request(db_user, db.Torrent(torrent_hash))
        logger.info(
            f"User {user['username']} made a request for torrent {torrent_hash}"
        )

    return "Request created successfully", 201


@g_app.route("/api/request/delete/<torrent_hash>", methods=["DELETE"])
@login_required
async def delete_request(user: jellyfin.JellyfinSession, torrent_hash: str):
    res = await g_db.cancel_request(
        db.User(id=user["id"], username=user["username"]), db.Torrent(torrent_hash)
    )
    if not res:
        logger.error(f"Failed to delete request for {torrent_hash}")
        return "Request not found", 404
    return "Request deleted successfully", 200


if __name__ == "__main__":
    g_app.secret_key = os.getenv("MOVIE_REQUEST_SERVER_SECRET")
    g_app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.getenv("MOVIE_REQUEST_SERVER_PORT", 5000)),
    )
