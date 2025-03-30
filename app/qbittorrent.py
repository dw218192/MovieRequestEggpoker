import httpx
import os
import logging
import contextlib
import enum
import httpx
import asyncio
import pathlib
from requests_toolbelt.multipart.encoder import MultipartEncoder

from typing import TypedDict

logger = logging.getLogger(__name__)

# libtorrent requires the following sys-level deps on windows
# 1. libssl
# 2. libcrypto
# 3. vcruntime140.dll

if os.name == "nt":
    import os
    import pathlib

    # Load the DLLs for Windows
    extra_dll_dir = pathlib.Path(__file__).parent / "deps" / "win"
    os.add_dll_directory(str(extra_dll_dir))

import libtorrent as lt


QBITTORRENT_PORT = os.getenv("QBITTORRENT_PORT", 8080)
QBITTORRENT_URL = f"http://localhost:{QBITTORRENT_PORT}/api/v2"
QBITTORRENT_DOWNLOAD_SUBFOLDER = os.getenv("QBITTORRENT_DOWNLOAD_SUBFOLDER", "")
QBITTORRENT_CATEGORY = os.getenv("QBITTORRENT_CATEGORY", "")


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


class TorrentState:
    ERROR = "error"
    MISSING_FILES = "missingFiles"
    UPLOADING = "uploading"
    PAUSED_UP = "pausedUP"
    QUEUED_UP = "queuedUP"
    STALLED_UP = "stalledUP"
    CHECKING_UP = "checkingUP"
    FORCED_UP = "forcedUP"
    ALLOCATING = "allocating"
    DOWNLOADING = "downloading"
    META_DL = "metaDL"
    PAUSED_DL = "pausedDL"
    QUEUED_DL = "queuedDL"
    STALLED_DL = "stalledDL"
    CHECKING_DL = "checkingDL"
    FORCED_DL = "forcedDL"
    CHECKING_RESUME_DATA = "checkingResumeData"
    MOVING = "moving"
    UNKNOWN = "unknown"


class TorrentInfo(TypedDict):
    added_on: int
    amount_left: int
    auto_tmm: bool
    availability: float
    category: str
    completed: int
    completion_on: int
    content_path: str
    dl_limit: int
    dlspeed: int
    downloaded: int
    downloaded_session: int
    eta: int
    f_l_piece_prio: bool
    force_start: bool
    hash: str
    isPrivate: bool
    last_activity: int
    magnet_uri: str
    max_ratio: float
    max_seeding_time: int
    name: str
    num_complete: int
    num_incomplete: int
    num_leechs: int
    num_seeds: int
    priority: int
    progress: float
    ratio: float
    ratio_limit: float
    save_path: str
    seeding_time: int
    seeding_time_limit: int
    seen_complete: int
    seq_dl: bool
    size: int
    state: str
    super_seeding: bool
    tags: str
    time_active: int
    total_size: int
    tracker: str
    up_limit: int
    uploaded: int
    uploaded_session: int
    upspeed: int


async def get_torrent_list(
    filter: GetTorrentListFilter = GetTorrentListFilter.ALL,
    hashes: list[str] | None = None,
    category: str | None = None,
) -> list[TorrentInfo] | None:
    try:
        async with async_client() as client:
            params = {"filter": str(filter)}
            if hashes:
                params["hashes"] = "|".join(hashes)
            if category:
                params["category"] = category
            response = await client.get("/torrents/info", params=params)
            if response.status_code != 200:
                logger.error(f"Error fetching torrent list: {response.status_code}")
                return None
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching torrent list: {e}")
        return None


async def add_torrent(
    *,
    torrent_links: str | list[str],
    save_path: str,
    root_folder=False,
    exist_ok=True,
) -> bool:
    if isinstance(torrent_links, str):
        torrent_links = [torrent_links]

    if not torrent_links:
        logger.error("No torrent links provided")
        return False

    save_path_ = pathlib.Path(save_path).absolute()
    if not save_path_.exists():
        logger.error(f"Save path does not exist: {save_path}")
        return False

    if QBITTORRENT_DOWNLOAD_SUBFOLDER:
        save_path_ = save_path_ / QBITTORRENT_DOWNLOAD_SUBFOLDER
        save_path_.mkdir(exist_ok=True)

    save_path = str(save_path_)

    torrent_hashes = [await get_torrent_hash(link) for link in torrent_links]
    if exist_ok:
        # need to check if the torrent is already added
        # or qbittorrent will treat this as an error
        if await get_torrent_list(hashes=torrent_hashes):
            logger.info(f"Torrents already added: {torrent_hashes}")
            return True

    try:
        fields = {
            "urls": "\n".join(torrent_hashes),
            "savepath": save_path,
            "root_folder": str(root_folder).lower(),
        }
        if QBITTORRENT_CATEGORY:
            fields["category"] = QBITTORRENT_CATEGORY

        encoder = MultipartEncoder(fields=fields)
        body = encoder.to_string()

        async with async_client() as client:
            response = await client.post(
                "/torrents/add",
                content=body,
                headers={
                    "Content-Type": encoder.content_type,
                },
            )
            if response.status_code != 200 and "fail" not in response.text.lower():
                logger.error(
                    f"Error adding torrents {torrent_links}: {response.status_code} {response.text}"
                )
                return False
            logger.info(f"Torrents {torrent_links} added successfully: {response.text}")
            return True
    except Exception as e:
        logger.error(f"Error adding torrents {torrent_links}: {e}")
        return False


async def delete_torrent(
    *,
    torrent_links: list[str] | str | None = None,
    torrent_hashes: list[str] | str | None = None,
    detete_files: bool = False,
) -> bool:
    if torrent_links and torrent_hashes:
        logger.error(
            "Both torrent_link and torrent_hashes provided. Only one is allowed."
        )
        return False
    if not torrent_links and not torrent_hashes:
        logger.error("Either torrent_link or torrent_hashes must be provided.")
        return False

    if torrent_links:
        if isinstance(torrent_links, str):
            torrent_links = [torrent_links]
        torrent_hashes = await asyncio.gather(
            *[get_torrent_hash(link) for link in torrent_links]
        )
    else:
        if isinstance(torrent_hashes, str):
            torrent_hashes = [torrent_hashes]

    assert (
        isinstance(torrent_hashes, list) and torrent_hashes
    ), "torrent_hashes must be a non-empty list"

    try:
        async with async_client() as client:
            response = await client.post(
                "/torrents/delete",
                data={
                    "hashes": "|".join(torrent_hashes),
                    "deleteFiles": str(detete_files).lower(),
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if response.status_code != 200:
                logger.error(
                    f"Error deleting torrents {torrent_hashes}: {response.status_code} {response.text}"
                )
                return False
            return True
    except Exception as e:
        logger.error(f"Error deleting torrents {torrent_hashes}: {e}")
        return False


async def get_torrent_hash(link_or_content: str, timeout_s: float = 50) -> str:
    if link_or_content.startswith("magnet:"):
        info = lt.parse_magnet_uri(link_or_content)  # type: ignore
        return str(info.info_hash)
    elif link_or_content.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s, follow_redirects=True
            ) as client:
                response = await client.get(link_or_content)
                if response.status_code != 200:
                    logger.error(f"Error : {response.status_code}")
                    return ""
                info = lt.torrent_info(lt.bdecode(response.content))  # type: ignore
                return str(info.info_hash())
        except httpx.UnsupportedProtocol as e:
            url = e.request.url
            if url.scheme == "magnet":
                new_url = "magnet:" + url.raw_path.decode().lstrip("/")
                return await get_torrent_hash(new_url, timeout_s)
            raise e
    else:
        info = lt.torrent_info(lt.bdecode(link_or_content))  # type: ignore
        return str(info.info_hash())


if __name__ == "__main__":
    import app.storage
    import tempfile

    logger.setLevel(logging.DEBUG)

    TEST_MAGNET_LINK = "https://webtorrent.io/torrents/big-buck-bunny.torrent"
    TEST_MAGNET = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"

    save_path = app.storage.get_best_path(400)
    if not save_path:
        save_path = tempfile.gettempdir()

    loop = asyncio.get_event_loop()
    task = add_torrent(
        torrent_links=[TEST_MAGNET],
        save_path=save_path,
    )
    if loop.run_until_complete(task):
        print(f"Torrent added successfully, download dir = {save_path}")
    else:
        print("Failed to add torrent")
        exit(1)

    input("Press Enter to continue...")
    task = delete_torrent(torrent_links=[TEST_MAGNET], detete_files=True)
    if loop.run_until_complete(task):
        print("Torrent deleted successfully")
    else:
        print("Failed to delete torrent")
        exit(1)

    input("Press Enter to continue...")

    cases = [
        TEST_MAGNET_LINK,
        TEST_MAGNET,
    ]

    tasks = []
    for case in cases:
        tasks.append(get_torrent_hash(case))

    results = loop.run_until_complete(asyncio.gather(*tasks))
    for case, result in zip(cases, results):
        print(f"{case[:min(30, len(case))]}... => {result}")
        assert result
