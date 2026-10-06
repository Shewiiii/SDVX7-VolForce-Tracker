import asyncio
import logging

import discord

from config import (
    DIFF_NAMES,
    EXCLUDE_DIFF_IN_HISTORY,
    SCORE_LOG_PATH,
    TOTAL_VOLFORCE_CACHE_PATH,
    USERNAME,
    VOLFORCE_HISTORY_PATH,
)
from tracker.performance_chart import load_performance_history, render_performance_graph
from tracker.total_volforce import load_total_volforce, load_volforce_history

from .state import BotState
from .views import CloseView

logger = logging.getLogger("sdvx_bot")


class Performance(discord.Cog):
    def __init__(self, state: BotState):
        self.state = state

    @discord.slash_command(
        name="performance",
        description=f"Graph {USERNAME}'s tracked current-play VolForce over time. Exclude NOV by default."[
            :100
        ],
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def performance(
        self,
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
        music = self.state.music
        music.refresh()
        days = {"day": 1, "week": 7, "month": 30, "3 months": 90, "all time": 0}[period]
        try:
            plays = await asyncio.to_thread(
                load_performance_history,
                SCORE_LOG_PATH,
                self.state.user_id,
                self.state.user_id,
                music.levels,
                days,
                exclude_under=next(
                    (
                        index
                        for index, name in DIFF_NAMES.items()
                        if name == exclude_under
                    ),
                    None,
                ),
            )
            if not plays:
                await ctx.respond(
                    f"No non-Crash plays recorded for {USERNAME} matching the selected period and difficulty filter.",
                )
                return
            snapshot = await asyncio.to_thread(
                load_total_volforce, TOTAL_VOLFORCE_CACHE_PATH
            )
            volforce_history = await asyncio.to_thread(
                load_volforce_history, VOLFORCE_HISTORY_PATH, snapshot
            )
            image = await asyncio.to_thread(
                render_performance_graph,
                plays,
                f"Performance History, {period}",
                show_hours=period == "day",
                exclude_difficulty=exclude_under,
                total_volforce=snapshot["value"] if snapshot else None,
                volforce_history=volforce_history,
            )
            await ctx.respond(
                file=discord.File(image, filename="performance.png"),
                view=CloseView(ctx.author.id),
            )
        except (OSError, ValueError) as error:
            logger.error("Performance graph failed: %s", error)
            await ctx.respond("Could not read or render performance history.")
