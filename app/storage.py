import logging
import shutil
import os

logger = logging.getLogger(__name__)

MOUNT_POINTS = os.getenv("MOVIE_REQUEST_SERVER_MOUNT_POINTS", "").split(";")


def get_best_path(file_size_bytes: int) -> str | None:
    """
    Choose a disk mount point that has enough space to store a file of given size.
    Picks the one with the most free space among eligible ones.
    """
    candidates = []

    for path in MOUNT_POINTS:
        try:
            usage = shutil.disk_usage(path)
            if usage.free >= file_size_bytes:
                candidates.append((usage.free, path))
        except FileNotFoundError:
            continue  # skip if mount point is missing

    if not candidates:
        return None  # No disk can hold the file

    # Return the mount point with most free space
    candidates.sort(reverse=True)
    return candidates[0][1]


if __name__ == "__main__":
    # Example usage
    file_size = 10 * 1024 * 1024 * 1024  # 10 GB
    best_path = get_best_path(file_size)
    if best_path:
        print(f"Best path for {file_size} bytes: {best_path}")
    else:
        print("No suitable mount point found.")
