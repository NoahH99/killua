"""
Chat commands (say).
"""
import logging
from typing import List

import discord
from discord import app_commands

from services.rcon import RCONService
from utils.discord_helpers import is_admin, send_debug_embed, PastelColors

logger = logging.getLogger("mc-bot.commands.chat")


def create_chat_commands(
    mc_group: app_commands.Group,
    rcon_service: RCONService,
) -> None:
    """
    Register chat commands.

    Args:
        mc_group: Discord command group to add commands to.
        rcon_service: RCON service instance.
    """

    @mc_group.command(name="say", description="Broadcast a message in Minecraft chat")
    @app_commands.describe(
        message="Message to broadcast",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_say(
        interaction: discord.Interaction,
        message: str,
        private: bool = False,
        debug: bool = False,
    ):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "You are not allowed to use this command.",
                ephemeral=True,
            )
            return

        ephemeral = private
        await interaction.response.defer(ephemeral=ephemeral)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        ok, resp = await rcon_service.execute_command(f'say [Discord] {message}')
        debug_lines.append(f"RCON say result: ok={ok}, resp={resp}")

        if not ok:
            embed = discord.Embed(
                title="Say",
                description="Failed to send the message via RCON.",
                color=PastelColors.RED,
            )
        else:
            embed = discord.Embed(
                title="Say",
                description="Message broadcasted to the Minecraft server.",
                color=PastelColors.GREEN,
            )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if debug_enabled:
            await send_debug_embed(interaction, "say", debug_lines)
