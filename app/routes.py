import inspect
import logging
import functools
from .extensions import g_db, g_limiter
from dataclasses import dataclass, field
import contextlib

from flask import Blueprint, redirect, render_template, request, session
import app.jackett as jackett
import app.jellyfin as jellyfin
import app.qbittorrent as qbittorrent
import app.db as db
import app.storage as storage

main_bp = Blueprint("main", __name__)

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

@main_bp.route("/")
def index():
    if jellyfin.get_current_user() is None:
        return redirect("/login")
    return render_template("index.html")


@main_bp.route("/login", methods=["GET"])
def login_page():
    if jellyfin.get_current_user():
        return redirect("/")
    return render_template("login.html")


@main_bp.route("/fragment/search", methods=["POST"])
@login_required
@g_limiter.limit("1/second")
async def search(user: jellyfin.JellyfinSession):
    body = request.get_json()
    if not isinstance(body, dict):
        logger.error(f"Invalid search request body: {body}")
        return "Invalid request body", 400

    search_type = body.get("type", None)
    query = body.get("query", None)

    if not query:
        return "Please provide a non-empty query", 400

    entries: list[dict] = []
    if search_type == "magnet":
        # direct link is the same as sending a request
        info = await qbittorrent.get_torrent_info(query)
        if info is None:
            return "Invalid magnet link", 400
        entries.append(
            {
                "GuessedMetadata": jackett.guess_metadata(info.title),
                "Info": info,
            }
        )
    elif search_type == "text":
        jackett_entries = await jackett.search(query)
        if jackett_entries is not None:
            for jackett_entry in jackett_entries:
                link = jackett_entry.get("MagnetUri", None)
                if not link:
                    link = jackett_entry.get("Link", None)
                title = jackett_entry.get("Title", None)

                if not link or not title:
                    logger.warning(f"ignored invalid jackett entry: {jackett_entry}")
                    continue

                entry = {}
                entry["GuessedMetadata"] = jackett.guess_metadata(title)
                if "Seeders" in jackett_entry:
                    entry["Seeders"] = jackett_entry["Seeders"]
                    if "Peers" in jackett_entry:
                        entry["Leechers"] = jackett_entry["Peers"]

                entry["Info"] = qbittorrent.BasicTorrentInfo(
                    title=jackett_entry["Title"],
                    size=jackett_entry["Size"],
                    infohash=jackett_entry["InfoHash"],
                    link=link,
                )
                entries.append(entry)
    else:
        logger.error(f"Invalid search type: {search_type}")
        return "Invalid search type", 400

    with transient_user_data(user["id"]) as user_data:
        return render_template(
            "fragments/search_res.html",
            query=query,
            entries=entries,
            user_data=user_data,
        )


@main_bp.route("/fragment/qbittorrent/stats", methods=["GET"])
@login_required
@g_limiter.limit("1/second")
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


@main_bp.route("/fragment/user", methods=["GET"])
@login_required
async def user(user: jellyfin.JellyfinSession):
    return render_template("fragments/user.html", user=user)


@main_bp.route("/api/login", methods=["POST"])
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


@main_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@main_bp.route("/api/request", methods=["POST"])
@login_required
@g_limiter.limit("20/day")
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


@main_bp.route("/api/request/delete/<torrent_hash>", methods=["DELETE"])
@login_required
async def delete_request(user: jellyfin.JellyfinSession, torrent_hash: str):
    res = await g_db.cancel_request(
        db.User(id=user["id"], username=user["username"]), db.Torrent(torrent_hash)
    )
    if not res:
        logger.error(f"Failed to delete request for {torrent_hash}")
        return "Request not found", 404
    return "Request deleted successfully", 200
