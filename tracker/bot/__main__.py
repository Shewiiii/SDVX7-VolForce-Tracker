import asyncio
import json
import logging
import os
from io import BytesIO

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from config import (
    DIFF_NAMES,
    FOOTER,
    MUSIC_DB_PATH,
    PULLING_RATE,
    SCORE_LOG_PATH,
)
from tracker.bot.images import get_accent_color
from tracker.bot.scores import format_score_breakdown, get_grade_coeff
from tracker.bot.state import BotState
from tracker.music import MusicCatalog
from tracker.performance_chart import best_play_message, load_play_history

from . import register_commands

logger = logging.getLogger("sdvx_bot")

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_ID_RAW = os.getenv("USER_ID")

if not BOT_TOKEN or not USER_ID_RAW:
    raise ValueError("Missing BOT_TOKEN or USER_ID in .env file")

USER_ID = int(USER_ID_RAW)
state = BotState(USER_ID, MusicCatalog(MUSIC_DB_PATH))
state.music.refresh()

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)
register_commands(bot, state)

last_read_pos = 0


@bot.event
async def on_ready():
    global last_read_pos
    log_path = SCORE_LOG_PATH

    # Initialize to end of file: ignore past runs, only send new ones
    if log_path.exists():
        last_read_pos = log_path.stat().st_size
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
    if not log_path.exists():
        return

    curr_size = log_path.stat().st_size
    if curr_size <= last_read_pos:
        return

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(last_read_pos)
        new_lines = f.readlines()
        last_read_pos = f.tell()

    if not new_lines:
        return

    state.music.refresh()

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
            # New proxy records contain VF calculated for this specific play
            if "volforce" not in data:
                logger.info("Ignoring score without calculated VolForce: %s", data)
                continue
            mid = int(data["music_id"])
            diff_idx = int(data["diff_idx"])
            score = int(data["score"])
            volforce = int(data["volforce"])
            clear_type = int(data.get("clear_type", 0))

            song_title = state.music.titles.get(mid, f"Music #{mid}")
            diff_name = DIFF_NAMES.get(diff_idx, "UNK")
            level = state.music.levels.get(mid, {}).get(diff_idx, 0.0)
            _, grade = get_grade_coeff(score)

            # Determine cover image & accent color
            embed_color = discord.Color(0xE0218A)
            cover_bytes = await asyncio.to_thread(
                state.music.find_jacket, mid, diff_idx
            )
            if cover_bytes:
                dominant_rgb = await asyncio.to_thread(get_accent_color, cover_bytes)
                embed_color = discord.Color.from_rgb(*dominant_rgb)

            clear_names = {
                1: "Crash (×0.50)",
                2: "Effective (×1.00)",
                3: "Excessive (×1.02)",
                4: "Maxxive (×1.04)",
                5: "UC (×1.06)",
                6: "PUC (×1.10)",
            }

            embed = discord.Embed(
                title=f"{song_title}",
                description=(
                    f"**Difficulty:** {diff_name} ({level:.1f})\n"
                    f"**Score:** {score:,} ({grade})\n"
                    f"**Clear:** {clear_names.get(clear_type, 'Unknown')}\n"
                    f"**VolForce:** `{volforce / 1000:.3f}`"
                ),
                color=embed_color,
            )

            attachment = {}
            if cover_bytes:
                embed.set_thumbnail(url="attachment://jacket.png")
                attachment["file"] = discord.File(
                    BytesIO(cover_bytes), filename="jacket.png"
                )

            embed.add_field(
                name="Judgements (Early  |  Late)",
                value=format_score_breakdown(data),
                inline=False,
            )
            embed.set_footer(text=FOOTER)
            ranking_content = None
            if clear_type != 1:
                try:
                    if ranking_history is None:
                        ranking_history = await asyncio.to_thread(
                            load_play_history,
                            SCORE_LOG_PATH,
                            USER_ID,
                            USER_ID,
                            state.music.levels,
                        )
                    ranking_content = best_play_message(data, ranking_history)
                except (OSError, ValueError, TypeError, KeyError) as error:
                    logger.warning("Could not rank current play: %s", error)
            await user.send(content=ranking_content, embed=embed, **attachment)
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


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
