import httpx
import os
import logging
import contextlib
from typing import TypedDict, NotRequired, Literal
from guessit import guessit

JACKETT_HOST = os.getenv("JACKETT_HOST", "localhost")
JACKETT_PORT = os.getenv("JACKETT_PORT", 9117)
JACKETT_API_URL = f"http://{JACKETT_HOST}:{JACKETT_PORT}/api/v2.0"
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


class MetadataDict(TypedDict):
    """
    https://github.com/guessit-io/guessit/blob/develop/docs/properties.md
    """

    type: Literal["episode", "movie"]
    title: str
    alternative_title: NotRequired[str]
    container: NotRequired[str]  # e.g. "mkv", "mp4"
    date: NotRequired[str]
    year: NotRequired[int]
    week: NotRequired[int]
    release_group: NotRequired[str]
    website: NotRequired[str]
    season: NotRequired[int | list[int]]
    episode: NotRequired[int | list[int]]

    # video properties
    source: NotRequired[str]  # e.g. "BluRay", "WEB-DL"
    screen_size: NotRequired[str]  # e.g. "1080p", "720p"
    aspect_ratio: NotRequired[str]  # e.g. "16:9", "2.35:1"
    video_codec: NotRequired[str]  # e.g. "h264", "hevc"
    video_bit_rate: NotRequired[str]  # e.g. "4000kbps", "8000kbps"
    frame_rate: NotRequired[str]  # e.g. "24fps", "30fps"


def guess_metadata(raw_torrent_name: str) -> MetadataDict:
    """
    uses guessit to guess the metadata of a media file from its torrent name
    :param raw_torrent_name: the name of the torrent
    """
    return guessit(raw_torrent_name)


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
            return entries

    except Exception as e:
        logger.exception(f"Error searching for {query}: {e}")
        return None


if __name__ == "__main__":
    # Test the search function
    logger.setLevel(logging.DEBUG)

    print(guess_metadata("The.Matrix.1999.1080p.BluRay.x264.DTS-HD.MA.5.1-CHD"))
    print(guess_metadata("Silo.S01.1080p.WEBRip.x265-KONTRAST"))
