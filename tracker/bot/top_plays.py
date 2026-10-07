import asyncio
import logging
from io import BytesIO

import discord

from config import DIFF_NAMES, FOOTER, SCORE_LOG_PATH, USERNAME
from tracker.music import MusicCatalog
from tracker.performance_chart import load_play_history

from .images import get_accent_color
from .state import BotState
from .views import CloseView

logger = logging.getLogger("sdvx_bot")


def format_top_plays(plays: list[dict], music: MusicCatalog) -> str:
    lines = []
    for rank, play in enumerate(plays[:10], 1):
        mid, difficulty = play["music_id"], play["diff_idx"]
        artist = discord.utils.escape_markdown(
            str(music.artists.get(mid, "Unknown artist"))
        )[:120]
        title = discord.utils.escape_markdown(
            str(music.titles.get(mid, f"Music #{mid}"))
        )[:160]
        level = music.levels.get(mid, {}).get(difficulty, 0.0)
        lines.append(
            f"**{rank}.** {artist} - {title} · {DIFF_NAMES.get(difficulty, 'UNK')} "
            f"({level:.1f}) · `{play['play_vf']:.3f}`"
        )
    return "\n".join(lines)


class TopPlays(discord.Cog):
    def __init__(self, state: BotState):
        self.state = state

    @discord.slash_command(
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
        self,
        ctx: discord.ApplicationContext,
        period: discord.Option(
            str, choices=["day", "week", "month", "3 months", "all time"]
        ) = "week",  # type: ignore
    ) -> None:
        await ctx.defer()
        music = self.state.music
        music.refresh()
        days = {"day": 1, "week": 7, "month": 30, "3 months": 90, "all time": 0}[period]
        try:
            plays = await asyncio.to_thread(
                load_play_history,
                SCORE_LOG_PATH,
                self.state.user_id,
                self.state.user_id,
                music.levels,
                days,
            )
            ranked = sorted(
                plays,
                key=lambda play: (play["play_vf"], play["timestamp"]),
                reverse=True,
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
                description=format_top_plays(best, music),
                color=discord.Color(0xCBA6F7),
            )
            embed.set_footer(text=FOOTER)
            cover_bytes = await asyncio.to_thread(
                music.find_jacket, best[0]["music_id"], best[0]["diff_idx"]
            )
            if cover_bytes:
                dominant_rgb = await asyncio.to_thread(get_accent_color, cover_bytes)
                embed.color = discord.Color.from_rgb(*dominant_rgb)
                embed.set_thumbnail(url="attachment://best_play.png")
                await ctx.respond(
                    embed=embed,
                    file=discord.File(BytesIO(cover_bytes), filename="best_play.png"),
                    allowed_mentions=discord.AllowedMentions.none(),
                    view=CloseView(ctx.author.id),
                )
            else:
                await ctx.respond(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                    view=CloseView(ctx.author.id),
                )
        except (OSError, ValueError) as error:
            logger.error("Top plays failed: %s", error)
            await ctx.respond("Could not read top-play history.")
