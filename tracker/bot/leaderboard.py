import asyncio
import logging
from io import BytesIO

import discord

from config import DIFF_NAMES, FOOTER, SCORE_LOG_PATH, TOTAL_VOLFORCE_CACHE_PATH
from tracker.leaderboard import chart_mark, load_chart_plays
from tracker.song_search import SongSearch
from tracker.total_volforce import load_total_volforce

from .images import get_accent_color
from .scores import get_grade_name
from .state import BotState
from .views import CloseView

logger = logging.getLogger("sdvx_bot")
PAGE_SIZE = 10
CLEAR_NAMES = {
    0: "No clear",
    1: "Crash",
    2: "Effective",
    3: "Excessive",
    4: "Maxxive",
    5: "UC",
    6: "PUC",
}


async def chart_autocomplete(
    ctx: discord.AutocompleteContext,
) -> list[discord.OptionChoice]:
    charts = await asyncio.to_thread(ctx.cog.search.search, ctx.value or "")
    music = ctx.cog.state.music
    choices = []
    for mid, index in charts:
        artist = music.artists.get(mid, "Unknown artist")[:25]
        title = music.titles.get(mid, f"Music #{mid}")
        suffix = f" · {DIFF_NAMES.get(index, 'UNK')} ({music.levels[mid][index]:g})"
        title = title[: 100 - len(artist) - len(suffix) - 3]
        choices.append(
            discord.OptionChoice(
                name=f"{artist} - {title}{suffix}", value=f"{mid}:{index}"
            )
        )
    return choices


def build_leaderboard_embed(
    music,
    music_id: int,
    difficulty: int,
    plays: list[dict],
    mark: int | None,
    page: int = 0,
    color: discord.Color | None = None,
    has_jacket: bool = False,
) -> discord.Embed:
    artist = discord.utils.escape_markdown(
        music.artists.get(music_id, "Unknown artist")
    )
    title = discord.utils.escape_markdown(
        music.titles.get(music_id, f"Music #{music_id}")
    )
    level = music.levels.get(music_id, {}).get(difficulty, 0)
    embed = discord.Embed(
        title=f"{artist} - {title}"[:256],
        description=f"**Difficulty:** {DIFF_NAMES.get(difficulty, 'UNK')} ({level:.1f})\n**Clear Mark:** {CLEAR_NAMES.get(mark, 'Unknown')}",
        color=color or discord.Color(0xCBA6F7),
    )
    start = page * PAGE_SIZE
    lines = [
        f"**{rank}.** {play['score']:,} · {get_grade_name(play['score'])} · `{play['play_vf']:.3f}` · <t:{int(play['timestamp'].timestamp())}:R>"
        for rank, play in enumerate(plays[start : start + PAGE_SIZE], start + 1)
    ]
    pages = max(1, (len(plays) + PAGE_SIZE - 1) // PAGE_SIZE)
    embed.add_field(
        name=f"Plays · Page {page + 1}/{pages}",
        value="\n".join(lines) or "No recorded nonzero plays for this chart yet.",
        inline=False,
    )
    if has_jacket:
        embed.set_thumbnail(url="attachment://jacket.png")
    embed.set_footer(text=FOOTER)
    return embed


class LeaderboardView(CloseView):
    def __init__(self, owner_id: int, plays: list[dict], render):
        super().__init__(owner_id)
        self.page = 0
        self.pages = max(1, (len(plays) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.render = render
        if self.pages == 1:
            self.remove_item(self.previous)
            self.remove_item(self.next)
        self.previous.disabled = True

    async def show_page(self, interaction: discord.Interaction, change: int):
        self.page = max(0, min(self.pages - 1, self.page + change))
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == self.pages - 1
        await interaction.response.edit_message(embed=self.render(self.page), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, button, interaction):
        await self.show_page(interaction, -1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, button, interaction):
        await self.show_page(interaction, 1)


class Leaderboard(discord.Cog):
    def __init__(self, state: BotState):
        self.state = state
        self.search = SongSearch(state.music)

    @discord.slash_command(
        name="leaderboard",
        description="Show all recorded plays for a chart.",
        integration_types={
            discord.IntegrationType.guild_install,
            discord.IntegrationType.user_install,
        },
    )
    async def leaderboard(
        self,
        ctx: discord.ApplicationContext,
        search: discord.Option(
            str,
            description="Search a song, reading or artist, then select a chart.",
            autocomplete=chart_autocomplete,
        ),  # type: ignore
    ) -> None:
        await ctx.defer()
        music = self.state.music
        music.refresh()
        try:
            music_id, difficulty = map(int, search.split(":"))
            if music.levels.get(music_id, {}).get(difficulty, 0) <= 0:
                raise ValueError("Unknown chart")
        except ValueError:
            matches = await asyncio.to_thread(self.search.search, search)
            if len(matches) != 1:
                await ctx.respond(
                    "Select a song and difficulty from autocomplete."
                    if matches
                    else "No matching chart found."
                )
                return
            music_id, difficulty = matches[0]
        try:
            plays = await asyncio.to_thread(
                load_chart_plays,
                SCORE_LOG_PATH,
                self.state.user_id,
                music_id,
                difficulty,
            )
            snapshot = await asyncio.to_thread(
                load_total_volforce, TOTAL_VOLFORCE_CACHE_PATH
            )
            mark = chart_mark(snapshot, music_id, difficulty, plays)
            jacket = await asyncio.to_thread(music.find_jacket, music_id, difficulty)
            color = discord.Color(0xCBA6F7)
            if jacket:
                color = discord.Color.from_rgb(
                    *await asyncio.to_thread(get_accent_color, jacket)
                )

            def render(page):
                return build_leaderboard_embed(
                    music, music_id, difficulty, plays, mark, page, color, bool(jacket)
                )

            attachment = (
                {"file": discord.File(BytesIO(jacket), filename="jacket.png")}
                if jacket
                else {}
            )
            await ctx.respond(
                embed=render(0),
                view=LeaderboardView(ctx.author.id, plays, render),
                allowed_mentions=discord.AllowedMentions.none(),
                **attachment,
            )
        except (OSError, ValueError) as error:
            logger.error("Leaderboard failed: %s", error)
            await ctx.respond("Could not read chart play history.")
