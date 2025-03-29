import httpx
import os
import logging
import contextlib
import re

JACKETT_PORT = os.getenv("JACKETT_PORT", 9117)
JACKETT_API_URL = f"http://localhost:{JACKETT_PORT}/api/v2.0"
JACKETT_API_KEY = os.getenv("JACKETT_API_KEY")

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def async_client():
    async with httpx.AsyncClient(
        base_url=JACKETT_API_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    ) as client:
        yield client


def _infer_file_format(title: str) -> str:
    title = title.lower()

    # Define patterns with priority order
    formats = [
        ("remux", r"\bremux\b"),
        ("bluray", r"\bblu[-]?ray\b"),
        ("web-dl", r"\bweb[-\. ]?dl\b"),
        ("webrip", r"\bweb[-\. ]?rip\b"),
        ("hdtv", r"\bhdtv\b"),
        ("dvdrip", r"\bdvd[-\. ]?rip\b"),
        ("hdrip", r"\bhdrip\b"),
        ("x264", r"\bx264\b"),
        ("x265", r"\bx265\b|\bhevc\b"),
        ("h264", r"\bh\.?264\b"),
        ("h265", r"\bh\.?265\b"),
        ("mpeg", r"\bmpeg[-]?\d\b"),
        ("avi", r"\bavi\b"),
        ("divx", r"\bdivx\b"),
        ("cam", r"\bcam[- ]?rip?\b"),
        ("ts", r"\bhd?ts\b"),
        ("mp4", r"\bmp4\b"),
        ("mkv", r"\bmkv\b"),
    ]

    for name, pattern in formats:
        if re.search(pattern, title):
            return name
    return ""


async def search(query: str) -> list[dict] | None:
    try:
        async with async_client() as client:
            response = await client.get(
                "/indexers/all/results",
                params={
                    "apikey": JACKETT_API_KEY,
                    "Query": query,
                },
                timeout=20,
            )
            if response.status_code != 200:
                logger.error(f"Error searching for {query}: {response.status_code}")
                return None
            resp_json = response.json()
            if "Results" not in resp_json:
                logger.error(f"Unexpected response format: {resp_json}")
            entries = resp_json.get("Results", [])
            for entry in entries:
                # try to infer the file format from the torrent name
                if title := entry.get("Title", None):
                    if inferred_format := _infer_file_format(title):
                        entry["FileFormat"] = inferred_format

            return entries

    except Exception as e:
        logger.exception(f"Error searching for {query}: {e}")
        return None
