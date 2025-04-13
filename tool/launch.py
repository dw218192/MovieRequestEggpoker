import threading
import subprocess
import argparse
import pathlib
import signal
import sys
import json
import shutil
import os


def run_cmd(
    shutdown_event: threading.Event,
    file_handle,
    cmd: list[str],
    name: str = "server",
):
    print(f"[{name}] Starting subprocess: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=file_handle,
        stderr=file_handle,
        text=True,
    )

    shutdown_event.wait()

    try:
        print(f"[{name}] Received KeyboardInterrupt, shutting down subprocess")
        try:
            if sys.platform == "win32":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)
            print(f"[{name}] Subprocess exited cleanly")
        except:
            print(f"[{name}] Unable to terminate subprocess normally, killing it")
            proc.terminate()
            proc.wait()
            print(f"[{name}] Subprocess terminated")
    finally:
        file_handle.close()


def gen_docker_compose_override(
    storage_config_file: pathlib.Path, data_dir: pathlib.Path, log_dir: pathlib.Path
):
    """
    Generate a docker-compose.override.yml file that mounts the storage config file
    and the data and log directories.

    Returns the path to the generated docker compose override file.
    """
    with storage_config_file.open("r") as f:
        storage_config = json.load(f)

    if not isinstance(storage_config, list):
        raise ValueError("Storage config must be a list")

    volumes: list[tuple[str, str, str]] = []
    for config in storage_config:
        if not isinstance(config, dict):
            raise ValueError("Storage config must be a list of dictionaries")

        host_path = config.get("host_path")
        movie_request_server_mount = config.get("movie_request_server_mount")
        qbittorrent_mount = config.get("qbittorrent_mount")

        if (
            host_path is None
            or movie_request_server_mount is None
            or qbittorrent_mount is None
        ):
            raise ValueError(
                "Storage config must contain 'host_path', 'movie_request_server_mount' and 'qbittorrent_mount' keys"
            )

        if (
            not isinstance(host_path, str)
            or not isinstance(movie_request_server_mount, str)
            or not isinstance(qbittorrent_mount, str)
        ):
            raise ValueError(
                "Storage config must contain 'host_path', 'movie_request_server_mount' and 'qbittorrent_mount' keys"
            )

        volumes.append((host_path, movie_request_server_mount, qbittorrent_mount))

    OUTFILE_FORMAT = """
services:
 movie-request-server:
  environment:
    - MOVIE_REQUEST_SERVER_STORAGE_CONFIG_FILE={storage_config_file}
  volumes:
    - {data_dir}:/app/_data
    - {log_dir}:/app/_logs
    {volumes}
    """

    override_file = data_dir / "docker-compose.override.yml"
    shutil.copy(str(storage_config_file), str(data_dir / "storage_config.json"))

    with override_file.open("w") as f:
        f.write(
            OUTFILE_FORMAT.format(
                storage_config_file="/app/_data/storage_config.json",
                volumes="\n    ".join([f"- {v[0]}:{v[1]}" for v in volumes]),
                data_dir="./" + str(data_dir.relative_to(".")),
                log_dir="./" + str(log_dir.relative_to(".")),
            )
        )
    return override_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run multiple servers in parallel")
    parser.add_argument(
        "--storage-config",
        type=pathlib.Path,
        default="storage_config.json",
        help="Path to the storage config file",
    )
    parser.add_argument(
        "--data-dir", type=pathlib.Path, default="./_data", help="Directory to store data"
    )
    parser.add_argument(
        "--log-dir", type=pathlib.Path, default="./_logs", help="Directory to store logs"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the servers if they have already been started",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Run in production mode using docker compose",
    )
    parser.add_argument(
        "--clear-logs",
        action="store_true",
        help="Clear the logs before starting the servers",
    )
    args = parser.parse_args()

    if args.clear_logs:
        for log_file in args.log_dir.glob("*.log"):
            log_file.unlink()

    if not args.storage_config.exists():
        raise FileNotFoundError(f"Storage config file {args.storage_config} not found")

    if args.deploy:
        override_file = gen_docker_compose_override(
            args.storage_config, args.data_dir, args.log_dir
        )

        compose_command = [
            "docker-compose",
            "--env-file",
            ".env",
            "-f",
            "docker-compose.yml",
            "-f",
            str(override_file),
            "up",
            "--build",
        ]

        if args.restart:
            compose_command.append("--force-recreate")

        commands = [
            (compose_command, "docker-compose"),
        ]
    else:
        os.environ["MOVIE_REQUEST_SERVER_STORAGE_CONFIG_FILE"] = str(
            args.storage_config
        )
        commands = [
            (["uv", "run", "--", "python", "-m", "app.main"], "movie_request_server"),
        ]

        jackett_command = ["docker-compose", "up", "jackett"]
        if args.restart:
            jackett_command.append("--force-recreate")

        commands.append(
            (jackett_command, "jackett"),
        )

    shutdown_event = threading.Event()
    ts: list[threading.Thread] = []

    for cmd, name in commands:
        log_file: pathlib.Path = args.log_dir / f"{name}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handle = log_file.open("w")

        t = threading.Thread(
            target=run_cmd, args=(shutdown_event, file_handle, cmd, name)
        )
        t.start()
        ts.append(t)

    try:
        print("Main thread is running, press Ctrl+C to terminate all servers...")
        while True:
            pass
    except KeyboardInterrupt:
        print("Terminating all servers...")
        shutdown_event.set()
        for t in ts:
            t.join()
