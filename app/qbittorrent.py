import httpx
import os
import logging
import contextlib
import enum
import asyncio
import pathlib
import tempfile
from typing import Any
from dataclasses import dataclass
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


QBITTORRENT_HOST = os.getenv("QBITTORRENT_HOST", "localhost")
QBITTORRENT_PORT = os.getenv("QBITTORRENT_PORT", 8080)
QBITTORRENT_URL = f"http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}/api/v2"
QBITTORRENT_CATEGORY = os.getenv("QBITTORRENT_CATEGORY", "")


logger.info(f"libtorrent version: {lt.version}")  # type: ignore
logger.info(f"QBITTORRENT_URL: {QBITTORRENT_URL}")

# this might still not work correctly on windows
g_lt_session = lt.session({"listen_interfaces": "0.0.0.0:6881"})  # type: ignore


@contextlib.asynccontextmanager
async def tmp_torrent_session(magnet_link: str, timeout_s: float = 15):
    """Create a temporary libtorrent session to extract metadata from magnet links.
    Returns:
        lt.session: The temporary libtorrent session.
    """
    info = lt.parse_magnet_uri(magnet_link)  # type: ignore
    info.save_path = tempfile.gettempdir()

    handle = None
    try:
        handle = g_lt_session.add_torrent(info)
        timer = 0
        ret = None
        while (ret := handle.torrent_file()) is None and timer < timeout_s:
            await asyncio.sleep(1)
            timer += 1
        if ret is None:
            logger.error(f"Failed to get metadata for magnet link: {magnet_link}")
        yield ret
    finally:
        if handle:
            g_lt_session.remove_torrent(handle)


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
    exist_ok: bool = False,
    **kwargs: dict[str, Any],
) -> bool:
    if isinstance(torrent_links, str):
        torrent_links = [torrent_links]

    if not torrent_links:
        logger.error("No torrent links provided")
        return False

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
            **kwargs,
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
    delete_files: bool = False,
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
                    "deleteFiles": str(delete_files).lower(),
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


@dataclass(frozen=True)
class BasicTorrentInfo:
    title: str
    infohash: str
    size: int
    link: str

    @property
    def size_formatted(self) -> str:
        return f"{self.size / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def from_libtorrent(info, link: str) -> "BasicTorrentInfo":
        title = info.name()
        infohash = str(info.info_hash())
        size = info.total_size()
        return BasicTorrentInfo(
            title=title,
            infohash=infohash,
            size=size,
            link=link,
        )


async def get_torrent_info(
    link_or_content: str | bytes, timeout_s: float = 50
) -> BasicTorrentInfo | None:

    async def _impl(
        link_or_content: str | bytes, source_link: str, timeout_s: float
    ) -> BasicTorrentInfo | None:
        if isinstance(link_or_content, bytes):
            try:
                info = lt.torrent_info(lt.bdecode(link_or_content))  # type: ignore
                if info is None:
                    return None
                return BasicTorrentInfo.from_libtorrent(info, source_link)
            except Exception as e:
                logger.exception(f"Error parsing torrent: {e}")
                return None

        assert isinstance(link_or_content, str)

        if link_or_content.startswith("magnet:"):
            async with tmp_torrent_session(link_or_content, timeout_s) as info:
                if info is None:
                    return None
                return BasicTorrentInfo.from_libtorrent(info, link_or_content)
        elif link_or_content.startswith(("http://", "https://")):
            # either a torrent file link or a magnet link
            try:
                async with httpx.AsyncClient(
                    timeout=timeout_s, follow_redirects=True
                ) as client:
                    response = await client.get(link_or_content)
                    if response.status_code != 200:
                        logger.error(f"Error fetching torrent: {response.status_code}")
                        return None
                    return await _impl(response.content, link_or_content, timeout_s)
            except httpx.UnsupportedProtocol as e:
                url = e.request.url
                if url.scheme == "magnet":
                    new_url = "magnet:" + url.raw_path.decode().lstrip("/")
                    return await _impl(new_url, link_or_content, timeout_s)
                logger.exception(f"Unsupported protocol: {url.scheme}")
                return None

        logger.error(f"Invalid link or content: {link_or_content}")
        return None

    return await _impl(
        link_or_content,
        link_or_content if isinstance(link_or_content, str) else "",
        timeout_s,
    )


async def get_torrent_hash(link_or_content: str | bytes, timeout_s: float = 50) -> str:
    info = await get_torrent_info(link_or_content, timeout_s)
    return "" if info is None else info.infohash
