"""
Status and monitoring commands (status, players, tps, uptime).
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

import discord
from discord import app_commands

from config import Config
from services.aws import AWSService
from services.rcon import RCONService
from utils.discord_helpers import is_admin, send_debug_embed, status_color_from_state, PastelColors

logger = logging.getLogger("mc-bot.commands.status")


def create_status_commands(
    mc_group: app_commands.Group,
    aws_service: AWSService,
    rcon_service: RCONService,
    last_seen_launch_time_getter,
) -> None:
    """
    Register status monitoring commands.

    Args:
        mc_group: Discord command group to add commands to.
        aws_service: AWS service instance.
        rcon_service: RCON service instance.
        last_seen_launch_time_getter: Callable to get last seen launch time.
    """

    @mc_group.command(name="status", description="Show EC2, RCON, player, and idle status")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_status(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        try:
            state, launch_time = aws_service.get_instance_info()
            debug_lines.append(f"Instance state: {state}")
            debug_lines.append(f"Launch time (UTC): {launch_time}")
        except Exception as e:
            logger.error(f"Error getting instance info: {e}")
            debug_lines.append(f"Error getting instance info: {e}")
            embed = discord.Embed(
                title="Server Status",
                description="Could not get instance information.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "status", debug_lines)
            return

        player_info = await rcon_service.get_player_info()
        if player_info is None:
            rcon_ok = False
            player_count = None
            player_names = []
            debug_lines.append("RCON unreachable or failed to parse player list.")
        else:
            rcon_ok = True
            player_count, player_names = player_info
            debug_lines.append(f"RCON reachable, players: {player_count}, names={player_names}")

        # Get idle timer from the task
        from bot.tasks import BotTasks
        zero_player_minutes = last_seen_launch_time_getter().zero_player_minutes
        idle_str = f"{zero_player_minutes}/{Config.IDLE_MINUTES_BEFORE_STOP} minutes with 0 players"

        # Calculate uptime
        now = datetime.now(timezone.utc)
        uptime_str = "N/A"
        if state == "running":
            last_seen_running_launch_time = last_seen_launch_time_getter().last_seen_running_launch_time
            if not last_seen_running_launch_time and launch_time:
                last_seen_running_launch_time = launch_time
            if last_seen_running_launch_time:
                delta = now - last_seen_running_launch_time
                days = delta.days
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                uptime_str = f"{days}d {hours}h {minutes}m"
                debug_lines.append(f"Computed uptime: {uptime_str}")

        embed = discord.Embed(
            title="Server Status",
            color=status_color_from_state(state),
        )
        embed.add_field(name="EC2 State", value=f"`{state}`", inline=True)
        embed.add_field(name="RCON Reachable", value=("Yes" if rcon_ok else "No"), inline=True)
        embed.add_field(
            name="Players Online",
            value=(str(player_count) if player_count is not None else "Unknown"),
            inline=True,
        )
        embed.add_field(name="Idle Timer", value=idle_str, inline=False)
        embed.add_field(name="Approximate Uptime", value=uptime_str, inline=False)

        if player_names:
            embed.add_field(name="Player Names", value=", ".join(player_names), inline=False)

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        if debug_enabled:
            ip = aws_service.get_instance_public_ip()
            host = aws_service.get_rcon_host()
            debug_lines.append(f"Public IP: {ip}")
            debug_lines.append(f"RCON host: {host}")
            debug_lines.append(f"AWS Region: {Config.AWS_REGION}")
            debug_lines.append(f"Instance ID: {Config.EC2_INSTANCE_ID}")
            await send_debug_embed(interaction, "status", debug_lines)

    @mc_group.command(name="players", description="Show online players via RCON")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_players(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        info = await rcon_service.get_player_info()
        if info is None:
            debug_lines.append("get_player_info() returned None.")
            embed = discord.Embed(
                title="Players",
                description="Could not reach RCON or parse the player list.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "players", debug_lines)
            return

        count, names = info
        debug_lines.append(f"Player count: {count}, names={names}")

        if count == 0:
            embed = discord.Embed(
                title="Players",
                description="There are no players online.",
                color=PastelColors.BLUE,
            )
        else:
            name_list = ", ".join(names) if names else "Names unavailable"
            embed = discord.Embed(
                title="Players",
                description=f"{count} players online.",
                color=PastelColors.GREEN,
            )
            embed.add_field(name="Names", value=name_list, inline=False)

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        if debug_enabled:
            await send_debug_embed(interaction, "players", debug_lines)

    @mc_group.command(name="tps", description="Show Paper server TPS")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_tps(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        tps_vals = await rcon_service.get_tps()
        if not tps_vals:
            debug_lines.append("get_tps() returned None.")
            embed = discord.Embed(
                title="TPS",
                description="Could not get TPS (RCON or server might not be ready).",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "tps", debug_lines)
            return

        tps_1m, tps_5m, tps_15m = tps_vals
        debug_lines.append(f"TPS values: {tps_1m}, {tps_5m}, {tps_15m}")

        embed = discord.Embed(
            title="TPS",
            color=PastelColors.GREEN,
        )
        embed.add_field(name="Last 1 minute", value=f"{tps_1m:.2f}", inline=True)
        embed.add_field(name="Last 5 minutes", value=f"{tps_5m:.2f}", inline=True)
        embed.add_field(name="Last 15 minutes", value=f"{tps_15m:.2f}", inline=True)
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        if debug_enabled:
            await send_debug_embed(interaction, "tps", debug_lines)

    @mc_group.command(name="uptime", description="Approximate EC2 uptime")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_uptime(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        try:
            state, launch_time = aws_service.get_instance_info()
            debug_lines.append(f"Instance state: {state}, launch_time={launch_time}")
        except Exception as e:
            logger.error(f"Error getting instance info: {e}")
            debug_lines.append(f"Error getting instance info: {e}")
            embed = discord.Embed(
                title="Uptime",
                description="Could not get instance information.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "uptime", debug_lines)
            return

        if state != "running":
            embed = discord.Embed(
                title="Uptime",
                description=f"Instance is `{state}`, uptime is not available.",
                color=status_color_from_state(state),
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "uptime", debug_lines)
            return

        last_seen_running_launch_time = last_seen_launch_time_getter().last_seen_running_launch_time
        if not last_seen_running_launch_time and launch_time:
            last_seen_running_launch_time = launch_time
            debug_lines.append("Set last_seen_running_launch_time from EC2 LaunchTime.")

        if not last_seen_running_launch_time:
            embed = discord.Embed(
                title="Uptime",
                description="Uptime is not tracked yet.",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "uptime", debug_lines)
            return

        now = datetime.now(timezone.utc)
        delta = now - last_seen_running_launch_time
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        text = f"{days}d {hours}h {minutes}m"
        debug_lines.append(f"Computed uptime delta: {delta} ({text})")

        embed = discord.Embed(
            title="Uptime",
            description=f"Approximate uptime: {text}",
            color=PastelColors.GREEN,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        if debug_enabled:
            await send_debug_embed(interaction, "uptime", debug_lines)
