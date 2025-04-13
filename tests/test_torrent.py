import app.qbittorrent as qbittorrent
import asyncio
import pathlib


TEST_MAGNET_LINK = "https://webtorrent.io/torrents/big-buck-bunny.torrent"
TEST_MAGNET = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"
TEST_MAGNET_CONTENT = (
    pathlib.Path(__file__).parent / "assets" / "big-buck-bunny.torrent"
).read_bytes()
TEST_MAGNET_HASH = "dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c"


async def test_torrent_hash():
    cases = [
        [TEST_MAGNET_LINK, TEST_MAGNET_HASH],
        [TEST_MAGNET, TEST_MAGNET_HASH],
        [TEST_MAGNET_CONTENT, TEST_MAGNET_HASH],
    ]
    results = await asyncio.gather(
        *[qbittorrent.get_torrent_hash(link) for link, _ in cases]
    )
    for (link, expected), result in zip(cases, results):
        assert result == expected, f"Failed for {link}: {result} != {expected}"

    invalid_cases = [
        "http://www.google.com",
        b"junkcontent",
    ]
    results = await asyncio.gather(
        *[qbittorrent.get_torrent_hash(link) for link in invalid_cases]
    )
    for result in results:
        assert result == "", f"Failed for {result}"
