import asyncio
import hashlib
import json
import logging
import math
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from colorsys import rgb_to_hsv
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from PIL import Image

from config import (
    CACHE_DIR,
    DIFF_NAMES,
    EXCLUDE_DIFF_IN_HISTORY,
    MUSIC_DB_PATH,
    PULLING_RATE,
    SCORE_LOG_PATH,
    USERNAME,
)
from performance import (
    best_play_message,
    load_performance_history,
    load_play_history,
    render_performance_graph,
)

logger = logging.getLogger("sdvx_bot")

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_ID_RAW = os.getenv("USER_ID")
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")

if not BOT_TOKEN or not USER_ID_RAW:
    raise ValueError("Missing BOT_TOKEN or USER_ID in .env file")

USER_ID = int(USER_ID_RAW)

CACHE_DIR.mkdir(parents=True, exist_ok=True)


DIFF_SLOT_TAGS = {
    0: ("novice",),
    1: ("advanced",),
    2: ("exhaust",),
    3: ("infinite", "gravity", "heaven", "vivid", "exceed", "nabla"),
    4: ("maximum",),
    5: ("ultimate",),
}

artist_db = {}


# COLOR EXTRACTION & IMGUR UPLOAD


def get_accent_color(image_bytes: bytes, threshold: int = 50) -> tuple[int, int, int]:
    """Extract an accent color from image bytes."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image = image.resize((50, 50))
    pixels = list(image.getdata())

    color_counts = Counter(pixels)
    dominant_color = color_counts.most_common(1)[0][0]

    def color_distance(c1, c2):
        return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

    accent_color = dominant_color
    max_priority = -1

    for color, count in color_counts.items():
        if color_distance(dominant_color, color) > threshold:
            _, saturation, brightness = rgb_to_hsv(
                color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
            )
            priority = saturation * brightness * count

            if priority > max_priority:
                max_priority = priority
                accent_color = color

    return accent_color


def find_local_jacket(mid: int, diff_idx: int) -> bytes | None:
    """Find and read the jacket PNG from the game's data/music folder."""
    music_dir = Path(MUSIC_DB_PATH).parent.parent / "music"
    if not music_dir.is_dir():
        return None

    # Search for folder matching mid (e.g. 2388_silentflame_...)
    song_folders = [
        d
        for d in music_dir.iterdir()
        if d.is_dir() and (d.name == str(mid) or d.name.startswith(f"{mid}_"))
    ]
    if not song_folders:
        return None
    folder = song_folders[0]

    # Map diff_idx to expected jacket index (1-based)
    diff_to_jacket = {
        0: [1],
        1: [2, 1],
        2: [3, 2, 1],
        3: [4, 3, 1],
        4: [5, 4, 3, 1],
        5: [5, 4, 3, 1],
    }
    preferred_indices = diff_to_jacket.get(diff_idx, [1])

    for idx in preferred_indices:
        for suffix in [
            f"jk_{mid}_{idx}.png",
            f"jk_{mid}_{idx}_b.png",
            f"jk_{mid}_{idx}_s.png",
        ]:
            candidate = folder / suffix
            if candidate.is_file():
                try:
                    return candidate.read_bytes()
                except OSError as err:
                    logger.debug(
                        "Failed reading jacket candidate %s: %s", candidate, err
                    )

    # Generic fallback inside song folder
    for candidate in folder.glob(f"jk_{mid}_*.png"):
        try:
            return candidate.read_bytes()
        except OSError as err:
            logger.debug("Failed reading generic jacket %s: %s", candidate, err)

    return None


async def get_cover_dict(cover_bytes: bytes) -> dict:
    """Upload song cover to Imgur and cache the result + accent color."""
    cover_hash = hashlib.md5(cover_bytes).hexdigest()
    cache_file = CACHE_DIR / f"{cover_hash}.json"

    if cache_file.is_file():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:  # noqa: ASYNC230
                return json.load(f)
        except (OSError, json.JSONDecodeError) as err:
            logger.debug("Cache read failed for %s, regenerating: %s", cache_file, err)

    dominant_rgb = get_accent_color(cover_bytes)
    url = None

    if IMGUR_CLIENT_ID:
        try:
            headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
            form = aiohttp.FormData()
            form.add_field("image", cover_bytes)

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    "https://api.imgur.com/3/image", headers=headers, data=form
                ) as resp,
            ):
                if resp.status == 200:
                    data = await resp.json()
                    url = data.get("data", {}).get("link")
                else:
                    logger.error(
                        "Imgur upload failed (status %d): %s",
                        resp.status,
                        await resp.text(),
                    )
        except (aiohttp.ClientError, OSError) as e:
            logger.error("Imgur request error: %s", e)

    result = {
        "url": url,
        "cover_hash": cover_hash,
        "dominant_rgb": list(dominant_rgb),
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as f:  # noqa: ASYNC230
            json.dump(result, f, indent=2)
    except (OSError, TypeError) as e:
        logger.warning("Failed writing cache file %s: %s", cache_file, e)

    return result


# DATABASE & VOLFORCE


def get_grade_coeff(score: int) -> tuple[float, str]:
    if score >= 9900000:
        return 1.05, "S"
    if score >= 9800000:
        return 1.02, "AAA+"
    if score >= 9700000:
        return 1.00, "AAA"
    if score >= 9500000:
        return 0.97, "AA+"
    if score >= 9300000:
        return 0.94, "AA"
    if score >= 9000000:
        return 0.91, "A+"
    if score >= 8700000:
        return 0.88, "A"
    if score >= 7500000:
        return 0.85, "B"
    if score >= 6500000:
        return 0.82, "C"
    return 0.80, "D"


def parse_music_db() -> tuple[dict[int, str], dict[int, dict[int, float]]]:
    title_map = {}
    level_map = {}

    if not os.path.exists(MUSIC_DB_PATH):
        logger.warning("music_db.xml not found at: %s", MUSIC_DB_PATH)
        return title_map, level_map

    raw_content = ""
    for enc in ("cp932", "shift_jis", "utf-8"):
        try:
            with open(MUSIC_DB_PATH, "r", encoding=enc, errors="replace") as fh:
                data = fh.read()
            if "<music" in data:
                raw_content = data
                break
        except (OSError, UnicodeDecodeError) as err:
            logger.debug("Failed decoding %s with %s: %s", MUSIC_DB_PATH, enc, err)
            continue

    if not raw_content:
        logger.warning("Failed to read music_db XML file.")
        return title_map, level_map

    try:
        clean_xml = re.sub(r"<\?xml[^>]*\?>", "", raw_content, count=1).strip()
        root = ET.fromstring(clean_xml.encode("utf-8"))

        for music in root.findall(".//music"):
            try:
                mid = int(music.attrib.get("id", 0))
                info = music.find("info")
                title = (
                    info.find("title_name").text
                    if info is not None and info.find("title_name") is not None
                    else f"ID: {mid}"
                )
                title_map[mid] = title
                artist_db[mid] = (
                    info.findtext("artist_name", "Unknown artist")
                    if info is not None
                    else "Unknown artist"
                )

                diff_node = music.find("difficulty")
                if diff_node is not None:
                    levels = {}
                    for idx, tags in DIFF_SLOT_TAGS.items():
                        for tag in tags:
                            elem = diff_node.find(tag)
                            if elem is not None:
                                difnum = elem.find("difnum")
                                if difnum is not None and difnum.text:
                                    raw_val = float(difnum.text.strip())
                                    levels[idx] = (
                                        raw_val / 10.0 if raw_val > 20 else raw_val
                                    )
                                break
                    level_map[mid] = levels
            except (ValueError, TypeError, KeyError, AttributeError) as err:
                logger.debug("Skipping invalid music entry: %s", err)
                continue

        logger.info("Successfully loaded %d songs from music_db.", len(title_map))
        return title_map, level_map
    except (ET.ParseError, ValueError, KeyError, AttributeError) as e:
        logger.error("XML parse error: %s", e)
        return title_map, level_map


title_db, level_db = parse_music_db()


def compute_vf(level: float, score: int, clear_coeff: float) -> float:
    grade_coeff, _ = get_grade_coeff(score)
    score_ratio = score / 10000000.0
    raw = level * score_ratio * grade_coeff * clear_coeff * 20.0
    return math.floor(raw) * 0.001


# BOT LIFECYCLE & DISPATCH


def format_score_breakdown(data: dict) -> str:
    """Display only transmitted counters; missing counts are not zero."""
    counts = data.get("score_breakdown") or {}

    def count(key: str) -> str:
        value = counts.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return f"{value:,}"
        return "—"

    if not counts:
        return "Judgment counts were not provided in this result."
    lines = [
        f"- {label}: {count(key)}"
        for label, key in (
            ("S-CRITICAL", "s_critical"),
            ("CRITICAL", "critical"),
            ("NEAR", "near"),
            ("ERROR", "error"),
        )
    ]
    return "\n".join(lines)


intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)

last_read_pos = 0


@bot.event
async def on_ready():
    global last_read_pos
    log_path = SCORE_LOG_PATH

    # Initialize to end of file: ignore past runs, only send new ones
    if os.path.exists(log_path):
        last_read_pos = os.path.getsize(log_path)
    else:
        last_read_pos = 0

    logger.info("Bot connected as %s (ID: %s)", bot.user, bot.user.id)
    logger.info(
        "Watching for NEW scores from position %d in %s", last_read_pos, log_path
    )

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="SOUND VOLTEX ∇"),
    )

    if not watch_score_log.is_running():
        watch_score_log.start()


@tasks.loop(seconds=PULLING_RATE)
async def watch_score_log():
    global last_read_pos
    log_path = SCORE_LOG_PATH
    if not os.path.exists(log_path):
        return

    curr_size = os.path.getsize(log_path)
    if curr_size <= last_read_pos:
        return

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:  # noqa: ASYNC230
        f.seek(last_read_pos)
        new_lines = f.readlines()
        last_read_pos = f.tell()

    if not new_lines:
        return

    try:
        user = await bot.fetch_user(USER_ID)
    except (discord.HTTPException, discord.NotFound) as e:
        logger.error("Failed to fetch user with ID %d: %s", USER_ID, e)
        return

    ranking_history = None
    for line in new_lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            # New proxy records contain VF calculated for this specific play.
            if "volforce" not in data:
                logger.info("Ignoring score without calculated VolForce: %s", data)
                continue
            mid = int(data["music_id"])
            diff_idx = int(data["diff_idx"])
            score = int(data["score"])
            volforce = int(data["volforce"])
            clear_type = int(data.get("clear_type", 0))

            song_title = title_db.get(mid, f"Music #{mid}")
            diff_name = DIFF_NAMES.get(diff_idx, "UNK")
            level = level_db.get(mid, {}).get(diff_idx, 0.0)
            _, grade_name = get_grade_coeff(score)

            # Determine cover image & accent color
            cover_url = None
            embed_color = discord.Color(0xE0218A)

            cover_bytes = find_local_jacket(mid, diff_idx)
            if cover_bytes:
                cover_meta = await get_cover_dict(cover_bytes)
                cover_url = cover_meta.get("url")
                dominant_rgb = cover_meta.get("dominant_rgb")
                if dominant_rgb and len(dominant_rgb) == 3:
                    embed_color = discord.Color.from_rgb(*dominant_rgb)

            clear_names = {
                1: "Crash (×0.50)",
                2: "Effective Clear (×1.00)",
                3: "Excessive Clear (×1.02)",
                4: "Maxxive Clear (×1.04)",
                5: "UC (×1.06)",
                6: "PUC (×1.10)",
            }

            embed = discord.Embed(
                title=f"{song_title}",
                description=(
                    f"**Difficulty:** {diff_name} ({level:.1f})\n"
                    f"**Score:** {score:,} ({grade_name})\n"
                    f"**Clear:** {clear_names.get(clear_type, 'Unknown')}\n"
                    f"**VolForce:** `{volforce / 1000:.3f}`"
                ),
                color=embed_color,
            )

            if cover_url:
                embed.set_thumbnail(url=cover_url)

            embed.add_field(
                name="Score breakdown",
                value=format_score_breakdown(data),
                inline=False,
            )
            embed.set_footer(text="SDVX ∇ VolForce Tracker")
            ranking_content = None
            if clear_type != 1:
                try:
                    if ranking_history is None:
                        ranking_history = await asyncio.to_thread(
                            load_play_history,
                            SCORE_LOG_PATH,
                            USER_ID,
                            USER_ID,
                            level_db,
                        )
                    ranking_content = best_play_message(data, ranking_history)
                except (OSError, ValueError, TypeError, KeyError) as error:
                    logger.warning("Could not rank current play: %s", error)
            await user.send(content=ranking_content, embed=embed)
            logger.info("Sent VolForce DM for mid=%d (%s) to %s", mid, song_title, user)
        except discord.Forbidden:
            logger.error(
                "Forbidden: Cannot send DMs to user %d (DMs disabled or no mutual server).",
                USER_ID,
            )
        except (
            json.JSONDecodeError,
            KeyError,
            ValueError,
            TypeError,
            discord.HTTPException,
        ) as e:
            logger.error("Failed to process line '%s': %s", line, e)


@watch_score_log.error
async def watch_score_log_error(error):
    logger.error("watch_score_log task encountered an error: %s", error)


# MISC COMMANDS


def format_top_plays(plays: list[dict]) -> str:
    lines = []
    for rank, play in enumerate(plays[:10], 1):
        mid, difficulty = play["music_id"], play["diff_idx"]
        artist = discord.utils.escape_markdown(
            str(artist_db.get(mid, "Unknown artist"))
        )[:120]
        title = discord.utils.escape_markdown(str(title_db.get(mid, f"Music #{mid}")))[
            :160
        ]
        level = level_db.get(mid, {}).get(difficulty, 0.0)
        lines.append(
            f"{rank}. {artist} - {title} - {DIFF_NAMES.get(difficulty, 'UNK')} "
            f"({level:.1f}) - `{play['play_vf']:.3f}`"
        )
    return "\n".join(lines)


@bot.slash_command(
    name="top-plays",
    description=f"Show {USERNAME}'s top 10 non-Crash plays by VolForce. Defaults to week."[
        :100
    ],
    integration_types={
        discord.IntegrationType.guild_install,
        discord.IntegrationType.user_install,
    },
)
async def top_plays(
    ctx: discord.ApplicationContext,
    period: discord.Option(
        str, choices=["day", "week", "month", "3 months", "all time"]
    ) = "week",  # type: ignore
) -> None:
    await ctx.defer()
    days = {"day": 1, "week": 7, "month": 30, "3 months": 90, "all time": 0}[period]
    try:
        plays = await asyncio.to_thread(
            load_play_history, SCORE_LOG_PATH, USER_ID, USER_ID, level_db, days
        )
        ranked = sorted(
            plays, key=lambda play: (play["play_vf"], play["timestamp"]), reverse=True
        )
        best = []
        seen_songs = set()
        for play in ranked:
            if play["music_id"] in seen_songs:
                continue
            seen_songs.add(play["music_id"])
            best.append(play)
            if len(best) == 10:
                break
        if not best:
            await ctx.respond(
                f"No non-Crash plays recorded for {USERNAME} in that period."
            )
            return
        embed = discord.Embed(
            title=f"Top 10 Plays, {period}",
            description=format_top_plays(best),
            color=discord.Color(0xCBA6F7),
        )
        embed.set_footer(text="SDVX ∇ VolForce Tracker")
        cover_bytes = await asyncio.to_thread(
            find_local_jacket, best[0]["music_id"], best[0]["diff_idx"]
        )
        if cover_bytes:
            dominant_rgb = await asyncio.to_thread(get_accent_color, cover_bytes)
            embed.color = discord.Color.from_rgb(*dominant_rgb)
            embed.set_thumbnail(url="attachment://best_play.png")
            await ctx.respond(
                embed=embed,
                file=discord.File(BytesIO(cover_bytes), filename="best_play.png"),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await ctx.respond(
                embed=embed, allowed_mentions=discord.AllowedMentions.none()
            )
    except (OSError, ValueError) as error:
        logger.error("Top plays failed: %s", error)
        await ctx.respond("Could not read top-play history.")


@bot.slash_command(
    name="performance",
    description=f"Graph {USERNAME}'s tracked current-play VolForce over time."[:100],
    integration_types={
        discord.IntegrationType.guild_install,
        discord.IntegrationType.user_install,
    },
)
async def performance(
    ctx: discord.ApplicationContext,
    period: discord.Option(
        str, choices=["day", "week", "month", "3 months", "all time"]
    ) = "all time",  # type: ignore
    exclude_under: discord.Option(
        str,
        description="Exclude this difficulty and all lower difficulties.",
        choices=list(DIFF_NAMES.values()),
    ) = EXCLUDE_DIFF_IN_HISTORY,  # type: ignore
) -> None:
    await ctx.defer()
    days = {"day": 1, "week": 7, "month": 30, "3 months": 90, "all time": 0}[period]
    try:
        plays = await asyncio.to_thread(
            load_performance_history,
            SCORE_LOG_PATH,
            USER_ID,
            USER_ID,
            level_db,
            days,
            exclude_under=next(
                (index for index, name in DIFF_NAMES.items() if name == exclude_under),
                None,
            ),
        )
        if not plays:
            await ctx.respond(
                f"No non-Crash plays recorded for {USERNAME} matching the selected period and difficulty filter.",
            )
            return
        image = await asyncio.to_thread(
            render_performance_graph,
            plays,
            f"Performance History, {period}",
            show_hours=period == "day",
            exclude_difficulty=exclude_under,
        )
        await ctx.respond(file=discord.File(image, filename="performance.png"))
    except (OSError, ValueError) as error:
        logger.error("Performance graph failed: %s", error)
        await ctx.respond("Could not read or render performance history.")


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
