"""
Admin commands (exec, op, deop, logs, diag).
"""
import logging
from datetime import datetime, timezone
from typing import List

import discord
from discord import app_commands

from config import Config
from services.aws import AWSService
from services.rcon import RCONService
from utils.discord_helpers import (
    is_admin,
    send_debug_embed,
    send_large_code_block,
    status_color_from_state,
    PastelColors,
)

logger = logging.getLogger("mc-bot.commands.admin")


def create_admin_commands(
    mc_group: app_commands.Group,
    aws_service: AWSService,
    rcon_service: RCONService,
    last_seen_launch_time_getter,
) -> None:
    """
    Register admin commands.

    Args:
        mc_group: Discord command group to add commands to.
        aws_service: AWS service instance.
        rcon_service: RCON service instance.
        last_seen_launch_time_getter: Callable to get last seen launch time.
    """

    @mc_group.command(name="exec", description="Execute a raw console command (admin only)")
    @app_commands.describe(
        command="Raw console command to execute",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_exec(
        interaction: discord.Interaction,
        command: str,
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

        logger.warning(f"RCON EXEC by {interaction.user} ({interaction.user.id}): {command}")
        debug_lines.append(f"Command issued by {interaction.user} ({interaction.user.id}): {command}")

        ok, resp = await rcon_service.execute_command(command)
        debug_lines.append(f"RCON exec result: ok={ok}, resp_len={len(resp) if resp else 0}")

        if not ok:
            embed = discord.Embed(
                title="Exec",
                description="Failed to execute the command via RCON.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            if debug_enabled:
                await send_debug_embed(interaction, "exec", debug_lines)
            return

        if resp is None:
            resp = ""
        if len(resp) > 1800:
            resp = resp[-1800:]
            debug_lines.append("Response was truncated to 1800 characters.")

        embed = discord.Embed(
            title="Exec",
            description="Command executed.",
            color=PastelColors.GREEN,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if resp:
            await interaction.followup.send(
                f"```log\n{resp}\n```",
                ephemeral=ephemeral,
            )

        if debug_enabled:
            await send_debug_embed(interaction, "exec", debug_lines)

    @mc_group.command(name="op", description="Grant operator status to a player")
    @app_commands.describe(
        player="Player name",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_op(
        interaction: discord.Interaction,
        player: str,
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

        ok, resp = await rcon_service.execute_command(f"op {player}")
        debug_lines.append(f"RCON op result: ok={ok}, resp={resp}")

        if not ok:
            embed = discord.Embed(
                title="OP Player",
                description="Failed to give operator status.",
                color=PastelColors.RED,
            )
        else:
            embed = discord.Embed(
                title="OP Player",
                description=f"Operator status granted to **{player}**.",
                color=PastelColors.GREEN,
            )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if resp:
            if len(resp) > 1800:
                resp = resp[-1800:]
                debug_lines.append("Response was truncated to 1800 characters.")
            await interaction.followup.send(
                f"```log\n{resp}\n```",
                ephemeral=ephemeral,
            )

        if debug_enabled:
            await send_debug_embed(interaction, "op", debug_lines)

    @mc_group.command(name="deop", description="Remove operator status from a player")
    @app_commands.describe(
        player="Player name",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_deop(
        interaction: discord.Interaction,
        player: str,
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

        ok, resp = await rcon_service.execute_command(f"deop {player}")
        debug_lines.append(f"RCON deop result: ok={ok}, resp={resp}")

        if not ok:
            embed = discord.Embed(
                title="DEOP Player",
                description="Failed to remove operator status.",
                color=PastelColors.RED,
            )
        else:
            embed = discord.Embed(
                title="DEOP Player",
                description=f"Operator status removed from **{player}**.",
                color=PastelColors.GREEN,
            )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if resp:
            if len(resp) > 1800:
                resp = resp[-1800:]
                debug_lines.append("Response was truncated to 1800 characters.")
            await interaction.followup.send(
                f"```log\n{resp}\n```",
                ephemeral=ephemeral,
            )

        if debug_enabled:
            await send_debug_embed(interaction, "deop", debug_lines)

    @mc_group.command(
        name="logs",
        description="View latest.log from CloudWatch (head or tail, admin only)"
    )
    @app_commands.describe(
        direction="Whether to show the start (head) or end (tail) of the log",
        lines="Number of log lines to show (1–500)",
        grep="Optional pattern to filter log lines (case-insensitive)",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    @app_commands.choices(direction=[
        app_commands.Choice(name="Tail (newest lines)", value="tail"),
        app_commands.Choice(name="Head (oldest lines)", value="head"),
    ])
    async def mc_logs(
        interaction: discord.Interaction,
        direction: app_commands.Choice[str],
        lines: int = 50,
        grep: str = None,
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

        lines = max(1, min(lines, 500))
        debug_lines.append(f"Requested direction={direction.value}, lines={lines}, grep={grep}")

        log_lines = aws_service.get_log_lines(direction.value, lines)
        if log_lines is None:
            debug_lines.append("get_log_lines() returned None (no group or error).")
            embed = discord.Embed(
                title="Logs",
                description="Log data is not available (CloudWatch not configured or no streams).",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            if debug_enabled:
                await send_debug_embed(interaction, "logs", debug_lines)
            return

        # Apply grep filter if provided
        if grep:
            original_count = len(log_lines)
            log_lines = [line for line in log_lines if grep.lower() in line.lower()]
            debug_lines.append(f"Grep filter applied: {original_count} -> {len(log_lines)} lines")

        if not log_lines:
            if grep:
                debug_lines.append(f"No lines matched grep pattern: {grep}")
                embed = discord.Embed(
                    title="Logs",
                    description=f"No log lines matched the pattern: `{grep}`",
                    color=PastelColors.YELLOW,
                )
            else:
                debug_lines.append("get_log_lines() returned empty list.")
                embed = discord.Embed(
                    title="Logs",
                    description="No log events found in the latest stream.",
                    color=PastelColors.YELLOW,
                )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            if debug_enabled:
                await send_debug_embed(interaction, "logs", debug_lines)
            return

        grep_info = f" (filtered by: `{grep}`)" if grep else ""
        embed = discord.Embed(
            title="Logs",
            description=f"{direction.name.capitalize()} of {lines} lines from the latest log stream{grep_info}.",
            color=PastelColors.BLUE,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        text = "\n".join(log_lines)
        debug_lines.append(f"Fetched {len(log_lines)} log lines.")

        await send_large_code_block(interaction, text, language="log", ephemeral=ephemeral)

        if debug_enabled:
            await send_debug_embed(interaction, "logs", debug_lines)

    @mc_group.command(name="diag", description="Detailed diagnostics (admin only)")
    @app_commands.describe(
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_diag(
        interaction: discord.Interaction,
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

        try:
            state, launch_time = aws_service.get_instance_info()
            debug_lines.append(f"Instance state: {state}")
            debug_lines.append(f"Launch time (UTC): {launch_time}")
        except Exception as e:
            logger.error(f"Error getting instance info: {e}")
            debug_lines.append(f"Error getting instance info: {e}")
            embed = discord.Embed(
                title="Diagnostics",
                description="Could not get instance information.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            if debug_enabled:
                await send_debug_embed(interaction, "diag", debug_lines)
            return

        rcon_ok = await rcon_service.is_reachable()
        debug_lines.append(f"RCON reachable: {rcon_ok}")

        player_info = await rcon_service.get_player_info()
        if player_info:
            player_count, player_names = player_info
            debug_lines.append(f"Players: {player_count}, names={player_names}")
        else:
            player_count, player_names = None, []
            debug_lines.append("get_player_info() returned None.")

        now = datetime.now(timezone.utc)
        uptime_str = "N/A"
        if state == "running":
            last_seen_running_launch_time = last_seen_launch_time_getter().last_seen_running_launch_time
            if not last_seen_running_launch_time and launch_time:
                last_seen_running_launch_time = launch_time
                debug_lines.append("Set last_seen_running_launch_time from LaunchTime.")
            if last_seen_running_launch_time:
                delta = now - last_seen_running_launch_time
                days = delta.days
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                uptime_str = f"{days}d {hours}h {minutes}m"
                debug_lines.append(f"Computed uptime: {uptime_str}")

        zero_player_minutes = last_seen_launch_time_getter().zero_player_minutes
        idle_str = f"{zero_player_minutes}/{Config.IDLE_MINUTES_BEFORE_STOP} minutes with 0 players"

        ip = aws_service.get_instance_public_ip()
        host = aws_service.get_rcon_host()

        short_ver, full_ver = await rcon_service.get_paper_version()
        debug_lines.append(f"Paper version: short={short_ver}, full={full_ver}")

        embed = discord.Embed(
            title="Diagnostics",
            color=status_color_from_state(state),
        )
        embed.add_field(name="EC2 State", value=f"`{state}`", inline=True)
        embed.add_field(name="AWS Region", value=Config.AWS_REGION, inline=True)
        embed.add_field(name="Instance ID", value=Config.EC2_INSTANCE_ID, inline=False)
        embed.add_field(name="Public IP", value=str(ip) if ip else "None", inline=True)
        embed.add_field(name="RCON Host", value=str(host) if host else "None", inline=True)
        embed.add_field(name="RCON Reachable", value=("Yes" if rcon_ok else "No"), inline=True)
        embed.add_field(
            name="Players Online",
            value=(str(player_count) if player_count is not None else "Unknown"),
            inline=True,
        )
        embed.add_field(name="Approximate Uptime", value=uptime_str, inline=False)
        embed.add_field(name="Idle Logic", value=idle_str, inline=False)

        if full_ver:
            embed.add_field(
                name="Paper / MC Version",
                value=full_ver,
                inline=False,
            )

        if Config.CF_DNS_RECORD_NAME:
            embed.add_field(name="Cloudflare DNS", value=Config.CF_DNS_RECORD_NAME, inline=False)

        if player_names:
            embed.add_field(
                name="Player Names",
                value=", ".join(player_names),
                inline=False,
            )

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if debug_enabled:
            debug_lines.append(f"CloudWatch log group: {Config.MC_CW_LOG_GROUP}")
            debug_lines.append(f"Cloudflare zone ID: {Config.CF_ZONE_ID}")
            await send_debug_embed(interaction, "diag", debug_lines)
