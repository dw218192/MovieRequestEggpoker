import threading
import subprocess
import argparse
import pathlib
import signal
import typing

if typing.TYPE_CHECKING:
    from _io import TextIOWrapper


def run_cmd(
    shutdown_event: threading.Event,
    file_handle: "TextIOWrapper",
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
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.wait(timeout=10)
            print(f"[{name}] Subprocess exited cleanly")
        except:
            print(f"[{name}] Unable to terminate subprocess normally, killing it")
            proc.terminate()
            proc.wait()
            print(f"[{name}] Subprocess terminated")
    finally:
        file_handle.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run multiple servers in parallel")
    parser.add_argument(
        "--log-dir", type=pathlib.Path, default="_logs", help="Directory to store logs"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the servers if they have already been started",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Run in production mode",
    )
    args = parser.parse_args()

    if args.prod:
        movie_request_server_cmd = [
            "gunicorn",
            "-c",
            "tool/gunicorn.conf.py",
            "app.main:init_app()",
        ]
    else:
        movie_request_server_cmd = ["uv", "run", "--", "python", "-m", "app.main"]
    commands = [
        (movie_request_server_cmd, "movie_request_server"),
    ]

    if args.restart:
        commands.append(
            (["docker-compose", "up", "--force-recreate", "jackett"], "jackett"),
        )
    else:
        commands.append(
            (["docker-compose", "up", "jackett"], "jackett"),
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
