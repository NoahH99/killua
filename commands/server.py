"""
Server control commands (start, stop, restart).
"""
import asyncio
import logging
from asyncio import sleep
from typing import List, Optional

import discord
from discord import app_commands

from config import Config
from services.aws import AWSService
from services.rcon import RCONService
from services.cloudflare import CloudflareService
from utils.discord_helpers import is_admin, send_debug_embed, PastelColors

logger = logging.getLogger("mc-bot.commands.server")

# Global variable for pending stop task
pending_stop_task: Optional[asyncio.Task] = None


def create_server_commands(
    mc_group: app_commands.Group,
    aws_service: AWSService,
    rcon_service: RCONService,
    cloudflare_service: CloudflareService,
) -> None:
    """
    Register server control commands.

    Args:
        mc_group: Discord command group to add commands to.
        aws_service: AWS service instance.
        rcon_service: RCON service instance.
        cloudflare_service: Cloudflare service instance.
    """

    @mc_group.command(name="start", description="Start the Minecraft EC2 instance")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_start(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        # Check state
        try:
            state = aws_service.get_instance_state()
            debug_lines.append(f"Initial instance state: {state}")
        except Exception as e:
            logger.error(f"Error checking instance state: {e}")
            debug_lines.append(f"Error checking instance state: {e}")
            embed = discord.Embed(
                title="Start Server",
                description="Could not check instance state.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "start", debug_lines)
            return

        # Already running
        if state == "running":
            ip = aws_service.get_instance_public_ip()
            debug_lines.append(f"Instance already running. Public IP: {ip}")

            connect_target = None
            if ip and Config.CF_DNS_RECORD_NAME:
                match, current = cloudflare_service.record_points_to_ip(ip)
                debug_lines.append(f"Cloudflare check: match={match}, current={current}")
                if match:
                    connect_target = Config.CF_DNS_RECORD_NAME

            if connect_target:
                desc = f"The Minecraft server is already running.\n\nConnect using: `{connect_target}`"
            elif ip:
                desc = f"The Minecraft server is already running.\n\nConnect using: `{ip}`"
            else:
                desc = "The Minecraft server is already running, but no public endpoint is available yet."

            # Get version
            short_ver, full_ver = await rcon_service.get_paper_version()
            debug_lines.append(f"Paper version: short={short_ver}, full={full_ver}")
            if short_ver:
                desc += f"\nVersion: {short_ver}"

            embed = discord.Embed(title="Start Server", description=desc, color=PastelColors.GREEN)
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)

            if debug_enabled:
                await send_debug_embed(interaction, "start", debug_lines)
            return

        # Transitional states
        if state in ("pending", "stopping"):
            embed = discord.Embed(
                title="Start Server",
                description=f"Instance is currently `{state}`. Try again soon.",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                debug_lines.append("Instance in transitional state; start aborted.")
                await send_debug_embed(interaction, "start", debug_lines)
            return

        # Start instance
        try:
            aws_service.start_instance()
            debug_lines.append("Called start_instance().")
        except Exception as e:
            logger.error(f"Failed to start instance: {e}")
            debug_lines.append(f"Failed to start instance: {e}")
            embed = discord.Embed(
                title="Start Server",
                description="Failed to start the instance.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "start", debug_lines)
            return

        # Send waiting message
        waiting_embed = discord.Embed(
            title="Start Server",
            description="Starting the Minecraft server. This may take a minute or two.",
            color=PastelColors.BLUE,
        )
        waiting_embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=waiting_embed)

        # Wait for running
        started = await aws_service.wait_for_instance_running()
        debug_lines.append(f"wait_for_instance_running() returned: {started}")

        if not started:
            embed = discord.Embed(
                title="Start Server",
                description="The instance did not reach the `running` state in time. Check the AWS console.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "start", debug_lines)
            return

        # Get IP
        ip = aws_service.get_instance_public_ip()
        debug_lines.append(f"Instance public IP after start: {ip}")

        if not ip:
            embed = discord.Embed(
                title="Start Server",
                description="The instance is running, but no public IP was found.",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "start", debug_lines)
            return

        # Update Cloudflare
        cf_success, cf_msg = cloudflare_service.update_a_record(ip)
        debug_lines.append(f"Cloudflare update: success={cf_success}, msg={cf_msg}")

        # Determine connection target
        connect_target = None
        if Config.CF_DNS_RECORD_NAME:
            match, current = cloudflare_service.record_points_to_ip(ip)
            debug_lines.append(f"Cloudflare check after update: match={match}, current={current}")
            if match:
                connect_target = Config.CF_DNS_RECORD_NAME

        # Wait for RCON
        rcon_ready = await rcon_service.wait_for_ready(poll_interval=5, timeout=240)
        debug_lines.append(f"RCON ready: {rcon_ready}")

        short_ver = None
        if rcon_ready:
            short_ver, full_ver = await rcon_service.get_paper_version()
            debug_lines.append(f"Paper version: short={short_ver}, full={full_ver}")
        else:
            debug_lines.append("RCON never became ready; skipping version info.")

        # Final message
        if connect_target:
            desc = f"The Minecraft server is now running.\n\nConnect using: `{connect_target}`"
        else:
            desc = f"The Minecraft server is now running.\n\nConnect using: `{ip}`"

        if short_ver:
            desc += f"\nVersion: {short_ver}"

        embed = discord.Embed(title="Start Server", description=desc, color=PastelColors.GREEN)
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        if debug_enabled:
            await send_debug_embed(interaction, "start", debug_lines)

    @mc_group.command(name="stop", description="Schedule the Minecraft EC2 instance to stop in 1 minute")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_stop(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        global pending_stop_task

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        # Check state
        try:
            state = aws_service.get_instance_state()
            debug_lines.append(f"Current instance state: {state}")
        except Exception as e:
            logger.error(f"Error checking instance state: {e}")
            debug_lines.append(f"Error checking instance state: {e}")
            embed = discord.Embed(
                title="Stop Server",
                description="Could not check instance state.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "stop", debug_lines)
            return

        # Already stopped
        if state == "stopped":
            embed = discord.Embed(
                title="Stop Server",
                description="The instance is already stopped.",
                color=PastelColors.BLUE,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "stop", debug_lines)
            return

        # Transitional states
        if state in ("stopping", "shutting-down", "terminated"):
            embed = discord.Embed(
                title="Stop Server",
                description=f"The instance is currently `{state}`.",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "stop", debug_lines)
            return

        # Check if stop already scheduled
        if pending_stop_task is not None and not pending_stop_task.done():
            embed = discord.Embed(
                title="Stop Server",
                description="A stop has already been scheduled. The server will shut down shortly.",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                debug_lines.append("Stop already scheduled.")
                await send_debug_embed(interaction, "stop", debug_lines)
            return

        # Announce shutdown
        embed = discord.Embed(
            title="Stop Server",
            description=(
                "The Minecraft server will stop in **1 minute**.\n"
                "Please wrap up what you're doing and disconnect."
            ),
            color=PastelColors.ORANGE,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        channel = interaction.channel
        requester = interaction.user
        debug_lines.append("Scheduling delayed stop in 60 seconds.")

        async def delayed_stop():
            global pending_stop_task
            try:
                # T-60 announcement
                try:
                    await rcon_service.execute_command(
                        "say §c[Server]§r The server will stop in §e60 seconds§r. Please wrap up!"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send RCON shutdown warning (60s): {e}")

                await asyncio.sleep(50)

                # T-10 announcement
                try:
                    await rcon_service.execute_command(
                        "say §c[Server]§r The server will stop in §e10 seconds§r."
                    )
                except Exception as e:
                    logger.warning(f"Failed to send RCON shutdown warning (10s): {e}")

                await asyncio.sleep(10)

                # Double-check state
                current_state = aws_service.get_instance_state()
                logger.info(f"Delayed stop fired; current state: {current_state}")

                if current_state != "running":
                    logger.info("Instance is no longer running; skipping stop")
                    return

                # Final announcement
                try:
                    await rcon_service.execute_command(
                        "say §c[Server]§r The server is §cstopping now§r."
                    )
                except Exception as e:
                    logger.warning(f"Failed to send final shutdown RCON message: {e}")

                await sleep(5)

                # Stop instance
                logger.info("Calling stop_instance() after delayed shutdown.")
                aws_service.stop_instance()

                # Announce in Discord
                if channel is not None:
                    stop_embed = discord.Embed(
                        title="Stop Server",
                        description="The Minecraft server is now stopping.",
                        color=PastelColors.RED,
                    )
                    stop_embed.set_footer(text=f"Originally requested by {requester}")
                    try:
                        await channel.send(embed=stop_embed)
                    except Exception as e:
                        logger.warning(f"Failed to send stop announcement: {e}")

            finally:
                pending_stop_task = None

        pending_stop_task = asyncio.create_task(delayed_stop())

        if debug_enabled:
            await send_debug_embed(interaction, "stop", debug_lines)

    @mc_group.command(name="restart", description="Restart the Minecraft EC2 instance")
    @app_commands.describe(debug="Show additional technical details (admin only)")
    async def mc_restart(interaction: discord.Interaction, debug: bool = False):
        await interaction.response.defer(ephemeral=False)

        debug_enabled = debug and is_admin(interaction)
        debug_lines: List[str] = []

        try:
            state = aws_service.get_instance_state()
            debug_lines.append(f"Current instance state: {state}")
        except Exception as e:
            logger.error(f"Error checking instance state: {e}")
            debug_lines.append(f"Error checking instance state: {e}")
            embed = discord.Embed(
                title="Restart Server",
                description="Could not check instance state.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "restart", debug_lines)
            return

        if state == "stopped":
            try:
                aws_service.start_instance()
                debug_lines.append("Instance was stopped; called start_instance().")
            except Exception as e:
                logger.error(f"Failed to start instance: {e}")
                debug_lines.append(f"Failed to start instance: {e}")
                embed = discord.Embed(
                    title="Restart Server",
                    description="Failed to start the instance.",
                    color=PastelColors.RED,
                )
                embed.set_footer(text=f"Requested by {interaction.user}")
                await interaction.followup.send(embed=embed)
                if debug_enabled:
                    await send_debug_embed(interaction, "restart", debug_lines)
                return

            embed = discord.Embed(
                title="Restart Server",
                description="The instance was stopped. Starting it now.",
                color=PastelColors.BLUE,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "restart", debug_lines)
            return

        if state in ("stopping", "shutting-down"):
            embed = discord.Embed(
                title="Restart Server",
                description=f"Instance is `{state}`, it cannot be restarted right now.",
                color=PastelColors.YELLOW,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                debug_lines.append("Restart aborted; instance in transitional state.")
                await send_debug_embed(interaction, "restart", debug_lines)
            return

        try:
            aws_service.stop_instance()
            debug_lines.append("Called stop_instance() for restart.")
        except Exception as e:
            logger.error(f"Failed to stop instance for restart: {e}")
            debug_lines.append(f"Failed to stop instance: {e}")
            embed = discord.Embed(
                title="Restart Server",
                description="Failed to stop the instance for restart.",
                color=PastelColors.RED,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            if debug_enabled:
                await send_debug_embed(interaction, "restart", debug_lines)
            return

        embed = discord.Embed(
            title="Restart Server",
            description="Stopping instance for restart. Use `/mc start` shortly to bring it back up.",
            color=PastelColors.BLUE,
        )
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

        if debug_enabled:
            await send_debug_embed(interaction, "restart", debug_lines)
