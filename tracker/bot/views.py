import discord


class CloseView(discord.ui.View):
    """Let only the requester (or DM recipient) dismiss this message."""

    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Only the person who requested this message can close it.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary)
    async def close(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            await interaction.followup.send(
                "Could not close this message. Please try again.", ephemeral=True
            )
            return
        self.stop()
