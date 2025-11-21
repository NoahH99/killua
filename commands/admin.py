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


def _create_progress_bar(value: float, max_value: float, length: int = 10) -> str:
    """Create a visual progress bar."""
    filled = int((value / max_value) * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"`{bar}`"


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
        lines="Number of log lines to show (1–250, or 1–5000 with grep)",
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

        # Higher limit when using grep to search through more lines
        max_lines = 5000 if grep else 250
        lines = max(1, min(lines, max_lines))
        debug_lines.append(f"Requested direction={direction.value}, lines={lines}, grep={grep}, max_lines={max_lines}")

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

    @mc_group.command(name="costs", description="View AWS costs for current and last month (admin only)")
    @app_commands.describe(
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_costs(
        interaction: discord.Interaction,
        private: bool = True,
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

        debug_lines.append("Fetching AWS cost data...")
        cost_data = aws_service.get_monthly_costs()

        if cost_data is None:
            debug_lines.append("get_monthly_costs() returned None (error fetching costs).")
            embed = discord.Embed(
                title="AWS Costs",
                description="Failed to fetch AWS cost data. Make sure Cost Explorer is enabled in your AWS account.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            if debug_enabled:
                await send_debug_embed(interaction, "costs", debug_lines)
            return

        debug_lines.append(f"Cost data retrieved successfully")
        debug_lines.append(f"Service breakdown: {cost_data.get('service_breakdown', {})}")
        debug_lines.append(f"EC2 current: ${cost_data['ec2_current']:.2f}, CloudWatch current: ${cost_data['cw_current']:.2f}")

        embed = discord.Embed(
            title="AWS Costs",
            description="Monthly cost breakdown for your AWS account and Minecraft server.",
            color=PastelColors.BLUE,
        )

        # ===== MINECRAFT SERVER COSTS =====
        embed.add_field(
            name="🎮 Minecraft Server Costs",
            value="_ _",  # Empty field for section header
            inline=False
        )

        embed.add_field(
            name=f"{cost_data['current_month_name']} (MTD)",
            value=f"${cost_data['mc_current']:.2f}",
            inline=True
        )

        embed.add_field(
            name=f"{cost_data['last_month_name']}",
            value=f"${cost_data['mc_last']:.2f}",
            inline=True
        )

        embed.add_field(
            name="Projected Total",
            value=f"**${cost_data['mc_projected']:.2f}**",
            inline=True
        )

        # Breakdown (EC2 + CloudWatch)
        embed.add_field(
            name="Breakdown",
            value=f"EC2: ${cost_data['ec2_current']:.2f} | CloudWatch: ${cost_data['cw_current']:.2f}",
            inline=False
        )

        # ===== TOTAL ACCOUNT COSTS =====
        embed.add_field(
            name="💳 Total AWS Account Costs",
            value="_ _",  # Empty field for section header
            inline=False
        )

        embed.add_field(
            name=f"{cost_data['current_month_name']} (MTD)",
            value=f"${cost_data['total_current']:.2f}",
            inline=True
        )

        embed.add_field(
            name=f"{cost_data['last_month_name']}",
            value=f"${cost_data['total_last']:.2f}",
            inline=True
        )

        embed.add_field(
            name="Projected Total",
            value=f"**${cost_data['total_projected']:.2f}**",
            inline=True
        )

        embed.set_footer(text=f"Requested by {interaction.user} | Data from AWS Cost Explorer")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if debug_enabled:
            await send_debug_embed(interaction, "costs", debug_lines)

    @mc_group.command(name="performance", description="View detailed EC2 performance metrics (admin only)")
    @app_commands.describe(
        period="Time period in minutes to analyze (1-60)",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_performance(
        interaction: discord.Interaction,
        period: int = 5,
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

        # Validate period
        period = max(1, min(period, 60))
        debug_lines.append(f"Fetching performance metrics for last {period} minutes...")

        # Check if instance is running
        try:
            state = aws_service.get_instance_state()
            debug_lines.append(f"Instance state: {state}")
            if state != "running":
                embed = discord.Embed(
                    title="Performance Metrics",
                    description=f"Instance is currently `{state}`. Performance metrics are only available when the instance is running.",
                    color=PastelColors.YELLOW,
                )
                embed.set_footer(text=f"Requested by {interaction.user}")
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
                if debug_enabled:
                    await send_debug_embed(interaction, "performance", debug_lines)
                return
        except Exception as e:
            logger.error(f"Error checking instance state: {e}")
            debug_lines.append(f"Error checking state: {e}")

        # Fetch performance metrics
        perf_data = aws_service.get_performance_metrics(period_minutes=period)

        if perf_data is None:
            debug_lines.append("get_performance_metrics() returned None.")
            embed = discord.Embed(
                title="Performance Metrics",
                description="Failed to fetch performance metrics from CloudWatch.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            if debug_enabled:
                await send_debug_embed(interaction, "performance", debug_lines)
            return

        debug_lines.append(f"Performance data retrieved successfully")

        metrics = perf_data['metrics']
        ec2_metrics = metrics.get('ec2', {})
        custom_metrics = metrics.get('custom', {})

        # Get instance info for more details
        instance_info = aws_service._get_instance()
        instance_state = instance_info.get('State', {}).get('Name', 'unknown')
        launch_time = instance_info.get('LaunchTime')

        # Calculate uptime
        uptime_str = "N/A"
        if launch_time:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            delta = now - launch_time
            days = delta.days
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            uptime_str = f"{days}d {hours}h {minutes}m"

        # ==== EXTRACT CPU METRICS FIRST (needed for health color) ====
        cpu_util = ec2_metrics.get('CPUUtilization')
        cpu_user = custom_metrics.get('cpu_usage_user')
        cpu_system = custom_metrics.get('cpu_usage_system')
        cpu_iowait = custom_metrics.get('cpu_usage_iowait')
        cpu_idle = custom_metrics.get('cpu_usage_idle')

        # Determine overall health color based on CPU
        health_color = PastelColors.GREEN
        if cpu_util and cpu_util['value'] > 80:
            health_color = PastelColors.RED
        elif cpu_util and cpu_util['value'] > 60:
            health_color = PastelColors.ORANGE

        embed = discord.Embed(
            title="🖥️ EC2 Performance Dashboard",
            color=health_color,
        )

        # Instance overview in description
        embed.description = (
            f"```\n"
            f"Instance Type: {perf_data['instance_type']}\n"
            f"Instance ID:   {perf_data['instance_id']}\n"
            f"State:         {instance_state}\n"
            f"Uptime:        {uptime_str}\n"
            f"Region:        {Config.AWS_REGION}\n"
            f"Period:        Last {period} minute(s)\n"
            f"```"
        )

        # ==== CPU METRICS ====
        if cpu_util or cpu_user:
            cpu_val = cpu_util['value'] if cpu_util else 0
            cpu_avg = cpu_util.get('average', cpu_val) if cpu_util else 0
            cpu_bar = _create_progress_bar(cpu_val, 100)

            cpu_main = f"{cpu_bar} **{cpu_val:.1f}%**"

            embed.add_field(
                name="💻 CPU Utilization",
                value=cpu_main,
                inline=True
            )

            # CPU breakdown in separate field
            if cpu_user or cpu_system or cpu_iowait or cpu_idle:
                breakdown = []
                if cpu_user:
                    breakdown.append(f"User: {cpu_user['value']:.1f}%")
                if cpu_system:
                    breakdown.append(f"System: {cpu_system['value']:.1f}%")
                if cpu_iowait:
                    breakdown.append(f"I/O Wait: {cpu_iowait['value']:.1f}%")
                if cpu_idle:
                    breakdown.append(f"Idle: {cpu_idle['value']:.1f}%")

                embed.add_field(
                    name="📊 CPU Breakdown",
                    value="\n".join(breakdown),
                    inline=True
                )

        # Add spacer for layout
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # ==== MEMORY METRICS ====
        mem_used_pct = custom_metrics.get('mem_used_percent')
        mem_avail = custom_metrics.get('mem_available')
        mem_used = custom_metrics.get('mem_used')
        mem_total = custom_metrics.get('mem_total')

        if mem_used_pct or mem_total:
            mem_val = mem_used_pct['value'] if mem_used_pct else 0
            mem_bar = _create_progress_bar(mem_val, 100)

            mem_main = f"{mem_bar} **{mem_val:.1f}%**"

            if mem_used and mem_total:
                mem_used_gb = mem_used['value'] / (1024**3)
                mem_total_gb = mem_total['value'] / (1024**3)
                mem_main += f"\n**{mem_used_gb:.2f} GB / {mem_total_gb:.2f} GB**"

            embed.add_field(
                name="🧠 Memory",
                value=mem_main,
                inline=True
            )

            # Memory details
            if mem_avail:
                mem_avail_mb = mem_avail['value'] / (1024**2)
                embed.add_field(
                    name="✅ Available Memory",
                    value=f"**{mem_avail_mb:.0f} MB**",
                    inline=True
                )

        # Add spacer for layout
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # ==== DISK USAGE ====
        disk_used_pct = custom_metrics.get('disk_used_percent')
        disk_free = custom_metrics.get('disk_free')

        if disk_used_pct or disk_free:
            disk_val = disk_used_pct['value'] if disk_used_pct else 0
            disk_bar = _create_progress_bar(disk_val, 100)

            disk_main = f"{disk_bar} **{disk_val:.1f}%**"

            if disk_free and disk_used_pct:
                disk_free_bytes = disk_free['value']
                disk_free_gb = disk_free_bytes / (1024**3)
                disk_total_bytes = disk_free_bytes / (1 - (disk_val / 100)) if disk_val < 100 else disk_free_bytes
                disk_used_gb = (disk_total_bytes - disk_free_bytes) / (1024**3)
                disk_total_gb = disk_total_bytes / (1024**3)

                disk_main += f"\n**{disk_used_gb:.1f} / {disk_total_gb:.1f} GB**"

            embed.add_field(
                name="💾 Disk (Root /)",
                value=disk_main,
                inline=True
            )

            if disk_free:
                disk_free_gb = disk_free['value'] / (1024**3)
                embed.add_field(
                    name="📁 Free Space",
                    value=f"**{disk_free_gb:.2f} GB**",
                    inline=True
                )

        # Add spacer for new row
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # ==== DISK I/O ====
        # Try CloudWatch Agent metrics first (more reliable)
        disk_read = custom_metrics.get('diskio_read_bytes')
        disk_write = custom_metrics.get('diskio_write_bytes')
        disk_read_ops = custom_metrics.get('diskio_reads')
        disk_write_ops = custom_metrics.get('diskio_writes')

        # Fall back to EC2 metrics if custom metrics not available
        if not disk_read:
            disk_read = ec2_metrics.get('DiskReadBytes')
        if not disk_write:
            disk_write = ec2_metrics.get('DiskWriteBytes')
        if not disk_read_ops:
            disk_read_ops = ec2_metrics.get('DiskReadOps')
        if not disk_write_ops:
            disk_write_ops = ec2_metrics.get('DiskWriteOps')

        if disk_read or disk_write:
            # Read operations
            if disk_read:
                read_bytes = disk_read['value']
                read_ops = disk_read_ops['value'] if disk_read_ops else 0
                # Show KB for small values, MB for larger
                if read_bytes < 1024**2:  # Less than 1 MB
                    read_str = f"**{read_bytes / 1024:.1f} KB**"
                else:
                    read_str = f"**{read_bytes / (1024**2):.1f} MB**"
                embed.add_field(
                    name="📥 Disk Read",
                    value=f"{read_str}\n{read_ops:.0f} ops",
                    inline=True
                )

            # Write operations
            if disk_write:
                write_bytes = disk_write['value']
                write_ops = disk_write_ops['value'] if disk_write_ops else 0
                # Show KB for small values, MB for larger
                if write_bytes < 1024**2:  # Less than 1 MB
                    write_str = f"**{write_bytes / 1024:.1f} KB**"
                else:
                    write_str = f"**{write_bytes / (1024**2):.1f} MB**"
                embed.add_field(
                    name="📤 Disk Write",
                    value=f"{write_str}\n{write_ops:.0f} ops",
                    inline=True
                )

            # Total I/O
            if disk_read and disk_write:
                total_io_bytes = disk_read['value'] + disk_write['value']
                if total_io_bytes < 1024**2:  # Less than 1 MB
                    total_str = f"**{total_io_bytes / 1024:.1f} KB**"
                else:
                    total_str = f"**{total_io_bytes / (1024**2):.1f} MB**"
                embed.add_field(
                    name="📀 Total Disk I/O",
                    value=total_str,
                    inline=True
                )

        # Add spacer for new row
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # ==== NETWORK METRICS ====
        # Try EC2 metrics first
        net_in = ec2_metrics.get('NetworkIn')
        net_out = ec2_metrics.get('NetworkOut')

        # Fall back to custom metrics if EC2 metrics not available
        if not net_in:
            net_in = custom_metrics.get('net_bytes_recv')
        if not net_out:
            net_out = custom_metrics.get('net_bytes_sent')

        if net_in or net_out:
            # Network In
            if net_in:
                in_mb = net_in['value'] / (1024**2)
                embed.add_field(
                    name="📥 Network In",
                    value=f"**{in_mb:.2f} MB**",
                    inline=True
                )

            # Network Out
            if net_out:
                out_mb = net_out['value'] / (1024**2)
                embed.add_field(
                    name="📤 Network Out",
                    value=f"**{out_mb:.2f} MB**",
                    inline=True
                )

            # Total + Throughput
            if net_in and net_out:
                total_mb = (net_in['value'] + net_out['value']) / (1024**2)
                throughput_mbps = (net_in['value'] + net_out['value']) * 8 / (period * 60 * 1024 * 1024)
                embed.add_field(
                    name="🌐 Total Traffic",
                    value=f"**{total_mb:.2f} MB**\n{throughput_mbps:.2f} Mbps",
                    inline=True
                )

        # Add spacer for new row
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # ==== ADDITIONAL INFO ====
        status_check = ec2_metrics.get('StatusCheckFailed')
        tcp_est = custom_metrics.get('netstat_tcp_established')

        # Health status
        if status_check:
            status_val = status_check['value']
            status_icon = "✅" if status_val == 0 else "❌"
            status_text = 'Healthy' if status_val == 0 else 'FAILED'
            embed.add_field(
                name="🏥 Health Status",
                value=f"{status_icon} **{status_text}**",
                inline=True
            )

        # TCP connections
        if tcp_est:
            embed.add_field(
                name="🔗 Connections",
                value=f"**{tcp_est['value']:.0f}** TCP",
                inline=True
            )

        # Network info
        if instance_info:
            public_ip = instance_info.get('PublicIpAddress', 'N/A')
            az = instance_info.get('Placement', {}).get('AvailabilityZone', 'N/A')
            embed.add_field(
                name="🌍 Location",
                value=f"**{az}**\n`{public_ip}`",
                inline=True
            )

        embed.set_footer(text=f"Requested by {interaction.user} | {perf_data['instance_id']} | Refresh every ~60s")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if debug_enabled:
            await send_debug_embed(interaction, "performance", debug_lines)

    @mc_group.command(name="autoshutdown", description="Configure auto-shutdown idle timeout (admin only)")
    @app_commands.describe(
        minutes="Idle minutes before auto-shutdown (1-120, or 0 to disable)",
        private="Send the response only to you",
        debug="Show additional technical details (admin only)",
    )
    async def mc_autoshutdown(
        interaction: discord.Interaction,
        minutes: int = None,
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

        # If no minutes provided, show current setting
        if minutes is None:
            current = Config.IDLE_MINUTES_BEFORE_STOP
            status = "enabled" if current > 0 else "disabled"

            embed = discord.Embed(
                title="Auto-Shutdown Configuration",
                description=f"Current auto-shutdown timeout: **{current} minutes** ({status})",
                color=PastelColors.BLUE,
            )
            embed.add_field(
                name="Usage",
                value="Use `/mc autoshutdown minutes:<value>` to change\n"
                      "• Set to `0` to disable auto-shutdown\n"
                      "• Set to `1-120` to enable with custom timeout",
                inline=False
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)

            if debug_enabled:
                debug_lines.append(f"Current setting: {current} minutes")
                await send_debug_embed(interaction, "autoshutdown", debug_lines)
            return

        # Validate and update the setting
        if minutes < 0 or minutes > 120:
            embed = discord.Embed(
                title="Auto-Shutdown Configuration",
                description="Invalid value. Please use 0 (disable) or 1-120 minutes.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            return

        old_value = Config.IDLE_MINUTES_BEFORE_STOP
        Config.IDLE_MINUTES_BEFORE_STOP = minutes
        debug_lines.append(f"Updated IDLE_MINUTES_BEFORE_STOP: {old_value} -> {minutes}")

        if minutes == 0:
            description = "Auto-shutdown has been **disabled**.\n\nThe server will not automatically stop when idle."
            color = PastelColors.YELLOW
        else:
            description = f"Auto-shutdown timeout set to **{minutes} minute{'s' if minutes != 1 else ''}**.\n\n"
            description += f"The server will automatically stop after {minutes} minute{'s' if minutes != 1 else ''} with 0 players online."
            color = PastelColors.GREEN

        embed = discord.Embed(
            title="Auto-Shutdown Configuration",
            description=description,
            color=color,
        )
        embed.add_field(
            name="Previous Setting",
            value=f"{old_value} minute{'s' if old_value != 1 else ''}",
            inline=True
        )
        embed.add_field(
            name="New Setting",
            value=f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes > 0 else "Disabled",
            inline=True
        )
        embed.add_field(
            name="Note",
            value="⚠️ This change is temporary and will reset when the bot restarts.\n"
                  "To make it permanent, update the `IDLE_MINUTES_BEFORE_STOP` environment variable.",
            inline=False
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        if debug_enabled:
            await send_debug_embed(interaction, "autoshutdown", debug_lines)

    @mc_group.command(name="metrics-debug", description="List available CloudWatch metrics (admin only)")
    @app_commands.describe(
        namespace="CloudWatch namespace to query (default: MinecraftServer)",
        private="Send the response only to you",
    )
    async def mc_metrics_debug(
        interaction: discord.Interaction,
        namespace: str = "MinecraftServer",
        private: bool = True,
    ):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "You are not allowed to use this command.",
                ephemeral=True,
            )
            return

        ephemeral = private
        await interaction.response.defer(ephemeral=ephemeral)

        # Get available metrics
        metrics = aws_service.list_available_metrics(namespace)

        if not metrics:
            embed = discord.Embed(
                title="Available Metrics",
                description=f"No metrics found in namespace `{namespace}`",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            return

        # Group metrics by name
        from collections import defaultdict
        metrics_by_name = defaultdict(list)
        for metric in metrics:
            metric_name = metric['MetricName']
            dims = ', '.join([f"{d['Name']}={d['Value']}" for d in metric.get('Dimensions', [])])
            metrics_by_name[metric_name].append(dims if dims else "no dimensions")

        # Build output - just show metric names with counts
        output_lines = []
        for metric_name in sorted(metrics_by_name.keys()):
            dims_list = metrics_by_name[metric_name]
            # Show first dimension combo as example
            example = dims_list[0] if dims_list else "no dimensions"
            if len(example) > 50:
                example = example[:47] + "..."
            output_lines.append(f"• **{metric_name}** ({len(dims_list)})\n  `{example}`")

        embed = discord.Embed(
            title=f"📊 Available Metrics: {namespace}",
            description=f"Found **{len(metrics)}** total metrics across **{len(metrics_by_name)}** metric names",
            color=PastelColors.BLUE,
        )

        # Split into multiple fields if needed (1024 char limit per field)
        current_chunk = []
        current_length = 0
        field_num = 1

        for line in output_lines:
            line_length = len(line) + 1  # +1 for newline
            if current_length + line_length > 1000:  # Leave some buffer
                # Send current chunk
                embed.add_field(
                    name=f"Metrics (Part {field_num})" if field_num > 1 else "Metrics",
                    value="\n".join(current_chunk),
                    inline=False
                )
                current_chunk = [line]
                current_length = line_length
                field_num += 1
            else:
                current_chunk.append(line)
                current_length += line_length

        # Add remaining lines
        if current_chunk:
            embed.add_field(
                name=f"Metrics (Part {field_num})" if field_num > 1 else "Metrics",
                value="\n".join(current_chunk),
                inline=False
            )

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
