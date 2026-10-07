from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .setup import (
    PYTHON_IMPORTS,
    REPO_ROOT,
    decoder_environment,
    find_decoder_root,
    node_tools,
)


def prepare() -> tuple[list[list[str]], dict[str, str], Path]:
    packages = subprocess.run(
        [sys.executable, "-c", PYTHON_IMPORTS],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if packages.returncode:
        raise RuntimeError("Python requirements are missing. Run setup.bat first.")
    # config loads this repository's .env, even when launched from another folder.
    from config import MUSIC_DB_PATH, SCORE_LOG_PATH

    legacy_score_log = REPO_ROOT / "score_log.txt"
    if legacy_score_log.is_file() and not SCORE_LOG_PATH.exists():
        SCORE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        legacy_score_log.rename(SCORE_LOG_PATH)

    if not os.getenv("BOT_TOKEN"):
        raise RuntimeError("BOT_TOKEN is missing. Run setup.bat to configure Discord.")
    user_id = os.getenv("USER_ID", "")
    if not user_id.isascii() or not user_id.isdecimal() or not 0 < int(user_id) < 2**64:
        raise RuntimeError(
            "USER_ID must be your numeric Discord user ID. Run setup.bat."
        )
    if not MUSIC_DB_PATH.is_file():
        raise RuntimeError(
            "music_db.xml was not found. Put SDVX7-VolForce-Tracker-main inside your game folder."
        )
    node, _ = node_tools()
    root = find_decoder_root(node)
    if root is None:
        raise RuntimeError("Protocol decoders are missing. Run setup.bat first.")
    env = decoder_environment(root)
    env.update(
        TRACKER_SCORE_LOG=str(SCORE_LOG_PATH),
    )
    try:
        port = int(env.get("TRACKER_PROXY_PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "TRACKER_PROXY_PORT must be a port between 1 and 65535."
        ) from None
    try:
        with socket.socket() as listener:
            if os.name == "nt":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", port))
    except OSError:
        raise RuntimeError(
            f"Port {port} is already in use. Close the other proxy before starting the tracker."
        ) from None
    commands = [
        [
            node,
            "-r",
            str(root / "node_modules/ts-node/register"),
            str(REPO_ROOT / "proxy/ea_proxy.ts"),
        ],
        [sys.executable, "-u", "-m", "tracker.bot"],
    ]
    return commands, env, root


def stop(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    processes = []
    try:
        commands, env, root = prepare()
        print(
            "Starting the proxy and Discord bot. Keep this window open.",
            flush=True,
        )
        for command, cwd in zip(commands, (root, REPO_ROOT)):
            processes.append(subprocess.Popen(command, cwd=cwd, env=env))
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        return 1
    except KeyboardInterrupt:
        print("Stopping the tracker...")
        return 0
    except (OSError, RuntimeError) as error:
        print(f"Cannot start tracker: {error}", file=sys.stderr)
        return 1
    finally:
        stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
