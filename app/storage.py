import logging
import shutil
import os

logger = logging.getLogger(__name__)


def parse_mount_points(mount_points: str) -> list[tuple[str, str]]:
    """
    Parse the mount points from the environment variable.
    """
    ret = []
    for mp in mount_points.split(";"):
        if not mp:
            continue
        if "|" in mp:
            qbittorrent_path, movie_request_server_path = mp.split("|")
        else:
            qbittorrent_path = mp
            movie_request_server_path = mp
        if not os.path.exists(movie_request_server_path):
            logger.warning(f"Mount point {movie_request_server_path} does not exist")
            continue
        ret.append((qbittorrent_path.strip(), movie_request_server_path.strip()))
    return ret

MOUNT_POINTS = parse_mount_points(os.getenv("MOVIE_REQUEST_SERVER_MOUNT_POINTS", ""))


def get_best_path(file_size_bytes: int) -> str | None:
    """
    Choose a disk mount point that has enough space to store a file of given size.
    Picks the one with the most free space among eligible ones.
    """
    candidates = []

    for qbittorrent_path, movie_request_server_path in MOUNT_POINTS:
        try:
            usage = shutil.disk_usage(movie_request_server_path)
            if usage.free >= file_size_bytes:
                candidates.append((usage.free, qbittorrent_path))
        except FileNotFoundError:
            continue  # skip if mount point is missing

    if not candidates:
        return None  # No disk can hold the file

    # Return the mount point with most free space
    candidates.sort(reverse=True)
    return candidates[0][1]


if __name__ == "__main__":
    # Example usage
    print(MOUNT_POINTS)
    file_size = 10 * 1024 * 1024 * 1024  # 10 GB
    best_path = get_best_path(file_size)
    if best_path:
        print(f"Best path for {file_size} bytes: {best_path}")
    else:
        print("No suitable mount point found.")
