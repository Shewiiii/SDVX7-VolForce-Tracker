import asyncio
import logging

import discord
from discord.ext import tasks

from config import GAME_LOG_PATH, PLAYTIME_STATE_PATH, PULLING_RATE
from tracker.playtime import PlaytimeTracker

logger = logging.getLogger("sdvx_bot")


class ActivePlaytime(discord.Cog):
    def __init__(self):
        self.tracker = PlaytimeTracker(GAME_LOG_PATH, PLAYTIME_STATE_PATH)

    @discord.Cog.listener()
    async def on_ready(self):
        if not self.collect_playtime.is_running():
            self.collect_playtime.start()
            logger.info("Tracking active gameplay from %s", GAME_LOG_PATH)

    def cog_unload(self):
        self.collect_playtime.cancel()

    @tasks.loop(seconds=PULLING_RATE)
    async def collect_playtime(self):
        try:
            # File scanning and locking run off the bot's event loop.
            await asyncio.to_thread(self.tracker.poll)
        except (OSError, ValueError, TypeError, KeyError) as error:
            logger.warning("Could not update active playtime: %s", error)

    @collect_playtime.error
    async def collect_playtime_error(self, error):
        logger.error("Active playtime task encountered an error: %s", error)
