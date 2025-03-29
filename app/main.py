import os
import functools
import logging
import inspect
from pathlib import Path

from flask import Flask, request, session, redirect, render_template
import app.jackett as jackett
import app.jellyfin as jellyfin
import app.qbittorrent as qbittorrent

g_app = Flask(__name__)

logger = logging.getLogger(__package__)


def login_required(f):
    if inspect.iscoroutinefunction(f):

        @functools.wraps(f)
        async def wrapper(*args, **kwargs):  # type:ignore
            user_session = jellyfin.get_current_user()
            if user_session is None:
                return "User not logged in", 401
            return await f(*args, **kwargs)

    else:

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user_session = jellyfin.get_current_user()
            if user_session is None:
                return "User not logged in", 401
            return f(*args, **kwargs)

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
async def search():
    body = request.get_json()
    if not isinstance(body, dict):
        logger.error(f"Invalid search request body: {body}")
        return "Invalid request body", 400

    search_type = body.get("type", None)
    query = body.get("query", None)

    if not query:
        return "Please provide a non-empty query", 400

    entries = await jackett.search(query)
    return render_template("fragments/search_res.html", query=query, entries=entries)


@g_app.route("/fragment/qbittorrent/stats", methods=["GET"])
@login_required
async def qbittorrent_stats():
    entries = await qbittorrent.get_torrent_list()
    return render_template("fragments/qbittorrent_stats.html", entries=entries)


@g_app.route("/fragment/user", methods=["GET"])
@login_required
def user():
    return render_template(
        "fragments/user.html", user=jellyfin.get_current_user(), requests=[]
    )


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


if __name__ == "__main__":
    g_app.secret_key = os.getenv("MOVIE_REQUEST_SERVER_SECRET")
    g_app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.getenv("MOVIE_REQUEST_SERVER_PORT", 5000)),
    )
