import os
import httpx
import logging
import contextlib
from dataclasses import dataclass
from typing import TypedDict

from flask import session
from typing import cast

JELLYFIN_PORT = os.getenv("JELLYFIN_PORT", 8096)
JELLYFIN_URL = f"http://localhost:{JELLYFIN_PORT}"
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")
if not JELLYFIN_API_KEY:
    raise ValueError("JELLYFIN_API_KEY environment variable is not set")

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def async_client():
    async with httpx.AsyncClient(
        base_url=JELLYFIN_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f'MediaBrowser Token="{JELLYFIN_API_KEY}"',
        },
    ) as client:
        yield client


JELLYFIN_SESSION_KEY = "jellyfin_user"


class JellyfinSession(TypedDict):
    id: str
    username: str
    token: str


def get_current_user() -> JellyfinSession | None:
    user = session.get(JELLYFIN_SESSION_KEY)
    if not user:
        return None
    return cast(JellyfinSession, user)


async def login(username: str, password: str) -> bool:
    try:
        logger.debug(f"Logging in to Jellyfin as {username}")
        async with async_client() as client:
            res = await client.post(
                f"/Users/AuthenticateByName",
                json={"Username": username, "Pw": password},
            )

            if res.status_code == 200:
                user_info = res.json()
                session[JELLYFIN_SESSION_KEY] = JellyfinSession(
                    id=user_info["User"]["Id"],
                    username=user_info["User"]["Name"],
                    token=user_info["AccessToken"],
                )
                return True
    except Exception as e:
        logger.exception(f"Error logging in to Jellyfin: {e}")
    return False
