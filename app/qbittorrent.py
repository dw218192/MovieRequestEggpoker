import httpx
import os
import logging
import contextlib
import enum
import qbittorrentapi

logger = logging.getLogger(__name__)

QBITTORRENT_PORT = os.getenv("QBITTORRENT_PORT", 8080)
QBITTORRENT_URL = f"http://localhost:{QBITTORRENT_PORT}/api/v2"


@contextlib.asynccontextmanager
async def async_client():
    async with httpx.AsyncClient(
        base_url=QBITTORRENT_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    ) as client:
        yield client


class GetTorrentListFilter(str, enum.Enum):
    ALL = "all"
    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    COMPLETED = "completed"
    PAUSED = "paused"
    ACTIVE = "active"
    INACTIVE = "inactive"
    RESUMED = "resumed"
    STALLED = "stalled"
    STALLED_UPLOADING = "stalled_uploading"
    STALLED_DOWNLOADING = "stalled_downloading"
    ERRORED = "errored"


async def get_torrent_list(
    filter: GetTorrentListFilter = GetTorrentListFilter.ALL,
) -> list[dict] | None:
    try:
        async with async_client() as client:
            response = await client.get(
                "/torrents/info", params={"filter": str(filter)}
            )
            if response.status_code != 200:
                logger.error(f"Error fetching torrent list: {response.status_code}")
                return None
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching torrent list: {e}")
        return None
