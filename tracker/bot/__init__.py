import discord

from .state import BotState


def register_commands(client: discord.Bot, state: BotState) -> None:
    from .performance import Performance
    from .profile import Profile
    from .top_plays import TopPlays

    client.add_cog(TopPlays(state))
    client.add_cog(Profile(state))
    client.add_cog(Performance(state))
