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


def check_packages(imports: str) -> None:
    packages = subprocess.run(
        [sys.executable, "-c", imports],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if packages.returncode:
        raise RuntimeError("Python requirements are missing. Run setup.bat first.")


def prepare() -> tuple[list[list[str]], dict[str, str], Path]:
    check_packages("import dotenv")
    # config loads this repository's .env, even when launched from another folder.
    from config import (
        DISCORD_ENABLED,
        MUSIC_DB_PATH,
        SCORE_LOG_PATH,
        VOLFORCE_HISTORY_PATH,
    )

    enable_discord = DISCORD_ENABLED
    if enable_discord:
        check_packages(PYTHON_IMPORTS)

    for destination in (SCORE_LOG_PATH, VOLFORCE_HISTORY_PATH):
        legacy_path = REPO_ROOT / "cache" / destination.name
        if legacy_path.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.rename(destination)

    if enable_discord:
        if not os.getenv("BOT_TOKEN"):
            raise RuntimeError(
                "BOT_TOKEN is missing. Run setup.bat to configure Discord."
            )
        user_id = os.getenv("USER_ID", "")
        if (
            not user_id.isascii()
            or not user_id.isdecimal()
            or not 0 < int(user_id) < 2**64
        ):
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
        TRACKER_VOLFORCE_HISTORY=str(VOLFORCE_HISTORY_PATH),
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
    ]
    if enable_discord:
        commands.append([sys.executable, "-u", "-m", "tracker.bot"])
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
        playtime = None
        next_poll = 0.0
        if len(commands) == 1:
            from config import GAME_LOG_PATH, PLAYTIME_STATE_PATH, PULLING_RATE
            from tracker.playtime import PlaytimeTracker

            playtime = PlaytimeTracker(GAME_LOG_PATH, PLAYTIME_STATE_PATH)
        print(
            "Starting the proxy"
            + (" (Discord disabled)" if playtime is not None else " and Discord bot")
            + ". Keep this window open.",
            flush=True,
        )
        for command, cwd in zip(commands, (root, REPO_ROOT)):
            processes.append(subprocess.Popen(command, cwd=cwd, env=env))
        while all(process.poll() is None for process in processes):
            if playtime is not None and time.monotonic() >= next_poll:
                try:
                    playtime.poll()
                except (OSError, ValueError, TypeError, KeyError) as error:
                    print(f"Could not update active playtime: {error}", file=sys.stderr)
                next_poll = time.monotonic() + PULLING_RATE
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
