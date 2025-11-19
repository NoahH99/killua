"""
Discord-specific utility functions.
"""
from typing import Optional, List

import discord

from config import Config


# Pastel color palette for embeds
class PastelColors:
    """Pastel color palette for Discord embeds."""
    GREEN = discord.Color.from_rgb(169, 223, 191)      # Pastel mint green
    RED = discord.Color.from_rgb(255, 179, 186)        # Pastel pink/red
    YELLOW = discord.Color.from_rgb(255, 223, 186)     # Pastel peach
    BLUE = discord.Color.from_rgb(174, 198, 207)       # Pastel blue
    PURPLE = discord.Color.from_rgb(203, 195, 227)     # Pastel lavender
    ORANGE = discord.Color.from_rgb(255, 204, 188)     # Pastel coral
    GREY = discord.Color.from_rgb(189, 195, 199)       # Pastel grey


def is_admin(interaction: discord.Interaction) -> bool:
    """
    Check if the interaction user is an admin.

    Args:
        interaction: Discord interaction to check.

    Returns:
        bool: True if user is admin, False otherwise.
    """
    return interaction.user.id == Config.ADMIN_DISCORD_ID


def status_color_from_state(state: str) -> discord.Color:
    """
    Get Discord color based on server state.

    Args:
        state: Server state string (running, stopped, etc.).

    Returns:
        discord.Color: Appropriate color for the state.
    """
    state = (state or "").lower()
    if state == "running":
        return PastelColors.GREEN
    if state in ("pending", "stopping"):
        return PastelColors.YELLOW
    if state in ("stopped", "shutting-down", "terminated"):
        return PastelColors.RED
    return PastelColors.GREY


async def send_large_code_block(
    interaction: discord.Interaction,
    text: str,
    language: str = "log",
    ephemeral: bool = False,
) -> None:
    """
    Send large text as multiple code block messages.

    Args:
        interaction: Discord interaction for sending messages.
        text: Text content to send.
        language: Code block language for syntax highlighting.
        ephemeral: Whether messages should be ephemeral.
    """
    max_len = 1900
    lines = text.splitlines()
    chunk = ""

    for line in lines:
        if len(chunk) + len(line) + 1 > max_len:
            if chunk:
                await interaction.followup.send(
                    f"```{language}\n{chunk}\n```",
                    ephemeral=ephemeral,
                )
            chunk = ""
        chunk += line + "\n"

    if chunk:
        await interaction.followup.send(
            f"```{language}\n{chunk}\n```",
            ephemeral=ephemeral,
        )


async def send_debug_embed(
    interaction: discord.Interaction,
    command_name: str,
    debug_lines: List[str],
) -> None:
    """
    Send debug information as an embed.

    Args:
        interaction: Discord interaction for sending the embed.
        command_name: Name of the command being debugged.
        debug_lines: List of debug message lines.
    """
    if not debug_lines:
        return

    text = "\n".join(debug_lines)
    if len(text) > 3900:
        text = text[-3900:]

    embed = discord.Embed(
        title=f"Debug - {command_name}",
        description=f"```text\n{text}\n```",
        color=PastelColors.GREY,
    )
    embed.set_footer(text=f"Requested by {interaction.user}")
    await interaction.followup.send(embed=embed, ephemeral=True)


async def update_bot_presence(
    bot: discord.Client,
    state: str,
    player_count: Optional[int]
) -> None:
    """
    Update the bot's Discord presence based on server status.

    Args:
        bot: Discord bot client.
        state: Server state.
        player_count: Number of players online.
    """
    state = (state or "").lower()

    # Default values
    status = discord.Status.online
    activity_text = "Minecraft: status unknown"

    if state == "running":
        # Server is up; choose message based on players
        if player_count is None:
            activity_text = "Minecraft: starting up..."
        elif player_count == 0:
            activity_text = "Minecraft: 0 players online"
        elif player_count == 1:
            activity_text = "Minecraft: 1 player online"
        else:
            activity_text = f"Minecraft: {player_count} players online"
        status = discord.Status.online

    elif state == "pending":
        activity_text = "Minecraft: starting..."
        status = discord.Status.idle

    elif state in ("stopping", "shutting-down"):
        activity_text = "Minecraft: stopping..."
        status = discord.Status.idle

    elif state in ("stopped", "terminated"):
        activity_text = "Minecraft: offline"
        status = discord.Status.idle

    else:
        activity_text = f"Minecraft: {state}"

    try:
        await bot.change_presence(
            status=status,
            activity=discord.Game(name=activity_text),
        )
    except Exception as e:
        # Don't log at warning level to avoid spam
        pass
