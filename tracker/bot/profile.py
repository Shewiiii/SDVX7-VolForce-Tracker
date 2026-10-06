import asyncio
import logging
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import discord

from config import (
    DIFF_NAMES,
    FOOTER,
    MUSIC_DB_PATH,
    SCORE_LOG_PATH,
    TOTAL_VOLFORCE_CACHE_PATH,
    USERNAME,
)
from tracker.music import MusicCatalog
from tracker.performance_chart import load_play_history
from tracker.timing import load_timing_summary
from tracker.total_volforce import load_total_volforce

from .scores import get_grade_name
from .state import BotState
from .views import CloseView

logger = logging.getLogger("sdvx_bot")


@lru_cache(maxsize=1)
def load_appeal_card_textures() -> dict[int, str]:
    """Use the game's mapping: card IDs do not always match texture filenames."""
    path = Path(MUSIC_DB_PATH).parent / "appeal_card.xml"
    try:
        raw = path.read_text(encoding="cp932", errors="replace")
        root = ET.fromstring(re.sub(r"<\?xml[^>]*\?>", "", raw, count=1))
        textures = {}
        for card in root.findall("card"):
            texture = card.findtext("info/texture", "").strip()
            card_id = card.get("id", "")
            if card_id.isdecimal() and re.fullmatch(r"[A-Za-z0-9_]+", texture):
                textures[int(card_id)] = texture
        return textures
    except (OSError, ET.ParseError, ValueError) as error:
        logger.warning("Could not load appeal-card artwork mapping: %s", error)
        return {}


def find_local_appeal_card(appeal_id: int | None) -> bytes | None:
    if type(appeal_id) is not int or appeal_id < 0:
        return None
    texture = load_appeal_card_textures().get(appeal_id)
    if not texture:
        return None
    path = Path(MUSIC_DB_PATH).parent.parent / "graphics" / "ap_card" / f"{texture}.png"
    try:
        return path.read_bytes()
    except OSError as error:
        logger.debug("Could not read appeal-card image %s: %s", path, error)
        return None


def build_profile_embed(
    snapshot: dict | None,
    history: list[dict],
    timing: dict | None = None,
    *,
    music: MusicCatalog,
) -> discord.Embed:
    player = snapshot["player"] if snapshot else {}
    name = discord.utils.escape_markdown(str(player.get("name") or USERNAME))[:100]
    embed = discord.Embed(title=f"{name}'s Profile", color=discord.Color(0xCBA6F7))
    code = player.get("sdvx_id") or player.get("code")
    if code:
        embed.add_field(name="SDVX ID", value=discord.utils.escape_markdown(str(code)))
    dan_names = {
        0: "Unranked",
        1: "1st Dan",
        2: "2nd Dan",
        3: "3rd Dan",
        **{level: f"{level}th Dan" for level in range(4, 12)},
        12: "∞ Dan",
    }
    for key, label in (
        ("skill_level", "Dan"),
        # ("gamecoin_packet", "Packets (PC)"),
        # ("gamecoin_block", "Blocks (BLC)"),
        # ("blaster_energy", "Blaster energy"),  # Always at 100% anyways
    ):
        value = player.get(key)
        if type(value) is int and value >= 0:
            display = (
                dan_names.get(value, f"Unknown Dan ({value})")
                if key == "skill_level"
                else f"{value:,}"
            )
            embed.add_field(name=label, value=display)

    def chart_text(chart: dict) -> str:
        mid, difficulty = chart["music_id"], chart["diff_idx"]
        title = discord.utils.escape_markdown(
            str(music.titles.get(mid, f"Music #{mid}"))
        )[:160]
        level = music.levels.get(mid, {}).get(difficulty)
        label = DIFF_NAMES.get(difficulty, "UNK")
        if level is not None:
            label += f" ({level:.1f})"
        return f"`{chart['volforce']:.3f}`\n{title} · {label}"

    if snapshot:
        embed.add_field(name="Total VolForce", value=f"`{snapshot['value']:.3f}`")
        embed.add_field(
            name="Saved charts",
            value=f"{snapshot['chart_count']:,} charts across {snapshot['song_count']:,} songs",
        )
        if snapshot["best_chart"]:
            embed.add_field(
                name="Best chart VolForce",
                value=chart_text(snapshot["best_chart"]),
                inline=False,
            )
            worst = snapshot["worst_top_chart"]
            value = chart_text(worst)
            embed.add_field(name="Lowest VolForce in top 50", value=value, inline=False)
            embed.add_field(
                name="Top 50 average", value=f"`{snapshot['top_average']:.3f}`"
            )

        records = snapshot["chart_records"]
        if records:
            clears = Counter(record["clear_type"] for record in records.values())
            clear_names = {
                0: "No clear",
                1: "Crash",
                2: "Effective",
                3: "Excessive",
                4: "Maxxive",
                5: "UC",
                6: "PUC",
            }
            embed.add_field(
                name="Clear Marks",
                value=" · ".join(
                    f"{clear_names[clear]}: {count:,}"
                    for clear, count in sorted(clears.items())
                ),
                inline=False,
            )
            grades = Counter(
                get_grade_name(record["score"]) for record in records.values()
            )
            embed.add_field(
                name="Grades",
                value=" · ".join(
                    f"{grade}: {grades[grade]:,}"
                    for grade in (
                        "S",
                        "AAA+",
                        "AAA",
                        "AA+",
                        "AA",
                        "A+",
                        "A",
                        "B",
                        "C",
                        "D",
                    )
                    if grades[grade]
                ),
                inline=False,
            )
        updated = int(snapshot["updated_at"].timestamp())
        captured = f"Charts: <t:{updated}:R>"
        if snapshot["player_updated_at"]:
            try:
                timestamp = datetime.fromisoformat(
                    snapshot["player_updated_at"].replace("Z", "+00:00")
                )
                if timestamp.tzinfo is not None:
                    captured += f"\nAccount details: <t:{int(timestamp.timestamp())}:R>"
            except (ValueError, TypeError, AttributeError):
                pass
        embed.add_field(name="Last captured", value=captured, inline=False)
        if not player:
            embed.description = (
                "Log into the game with your card to capture account details."
            )
    else:
        embed.description = (
            "Account details and Total VolForce are unavailable. Log into the game"
            " with your card to capture your saved profile."
        )
    if history:
        values = [play["play_vf"] for play in history]
        first, last = (
            int(history[index]["timestamp"].timestamp()) for index in (0, -1)
        )
        embed.add_field(
            name="Tracked non-Crash plays",
            value=f"{len(history):,} plays · Best {max(values):.3f} · Average {math.fsum(values) / len(values):.3f}"
            f"\nFirst: <t:{first}:f>\nLatest: <t:{last}:f>",
            inline=False,
        )
    else:
        embed.add_field(
            name="Tracked non-Crash plays",
            value="No local history available.",
            inline=False,
        )
    if timing is not None:
        ms = timing["average_ms"]
        embed.add_field(
            name="Estimated average timing",
            value=f"`{ms:+.1f} ms` ({'Early' if ms < 0 else 'Late' if ms > 0 else 'Neutral'})"
            f"\nBased on {timing['hits']:,} notes, across {timing['plays']:,} plays",
            inline=False,
        )
    else:
        embed.add_field(
            name="Estimated average timing",
            value="No valid, nonempty timing histograms saved yet.",
            inline=False,
        )
    embed.set_footer(text=f"{FOOTER} · RyuNET")
    return embed


class Profile(discord.Cog):
    def __init__(self, state: BotState):
        self.state = state

    @discord.slash_command(
        name="profile",
        description=f"Show {USERNAME}'s account, chart stats and top-50 VolForce."[
            :100
        ],
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def profile(self, ctx: discord.ApplicationContext) -> None:
        await ctx.defer()
        music = self.state.music
        music.refresh()
        snapshot = await asyncio.to_thread(
            load_total_volforce, TOTAL_VOLFORCE_CACHE_PATH
        )
        try:
            history = await asyncio.to_thread(
                load_play_history,
                SCORE_LOG_PATH,
                self.state.user_id,
                self.state.user_id,
                music.levels,
            )
        except (OSError, ValueError) as error:
            logger.warning("Could not load profile's local history: %s", error)
            history = []
        try:
            timing = await asyncio.to_thread(
                load_timing_summary, SCORE_LOG_PATH, self.state.user_id
            )
        except (OSError, ValueError) as error:
            logger.warning("Could not load timing history: %s", error)
            timing = None
        embed = build_profile_embed(snapshot, history, timing, music=music)
        appeal_id = snapshot["player"].get("appeal_id") if snapshot else None
        card_bytes = await asyncio.to_thread(find_local_appeal_card, appeal_id)
        attachment = {}
        if card_bytes:
            embed.set_thumbnail(url="attachment://appeal_card.png")
            attachment["file"] = discord.File(
                BytesIO(card_bytes), filename="appeal_card.png"
            )
        await ctx.respond(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
            view=CloseView(ctx.author.id),
            **attachment,
        )
