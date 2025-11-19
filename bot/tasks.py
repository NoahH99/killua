"""
Background tasks for the Discord bot.
"""
import logging
from datetime import datetime
from typing import Optional

import discord
from discord.ext import tasks

from config import Config
from services.aws import AWSService
from services.rcon import RCONService
from utils.discord_helpers import update_bot_presence

logger = logging.getLogger("mc-bot.tasks")


class BotTasks:
    """Manages background tasks for the bot."""

    def __init__(
        self,
        bot: discord.Client,
        aws_service: AWSService,
        rcon_service: RCONService,
    ):
        """
        Initialize bot tasks.

        Args:
            bot: Discord bot client.
            aws_service: AWS service instance.
            rcon_service: RCON service instance.
        """
        self.bot = bot
        self.aws_service = aws_service
        self.rcon_service = rcon_service

        # State tracking
        self.zero_player_minutes = 0
        self.last_seen_running_launch_time: Optional[datetime] = None

        # Create the task
        self._idle_check_task = tasks.loop(minutes=1)(self._idle_check)
        self._idle_check_task.before_loop(self._before_idle_check)

    def start(self) -> None:
        """Start all background tasks."""
        if not self._idle_check_task.is_running():
            self._idle_check_task.start()
            logger.info("Background tasks started")

    def stop(self) -> None:
        """Stop all background tasks."""
        if self._idle_check_task.is_running():
            self._idle_check_task.cancel()
            logger.info("Background tasks stopped")

    async def _before_idle_check(self) -> None:
        """Wait for bot to be ready before starting idle check."""
        await self.bot.wait_until_ready()
        logger.info("Idle check task initialized")

    async def _idle_check(self) -> None:
        """
        Background task that checks for idle server and updates presence.
        Runs every minute.
        """
        try:
            state, launch_time = self.aws_service.get_instance_info()
        except Exception as e:
            logger.error(f"Failed to get instance state: {e}")
            await update_bot_presence(self.bot, "unknown", None)
            return

        player_count: Optional[int] = None

        if state != "running":
            # Not running -> reset counters and update presence
            if self.zero_player_minutes != 0:
                logger.info("Instance not running, resetting zero_player_minutes")
            self.zero_player_minutes = 0
            self.last_seen_running_launch_time = None

            await update_bot_presence(self.bot, state, player_count)
            return

        # Instance is running – remember launch time
        if launch_time:
            self.last_seen_running_launch_time = launch_time

        # Try to get player count via RCON
        player_count = await self.rcon_service.get_player_count()
        if player_count is None:
            logger.info("Could not query player count (server may be starting)")
            await update_bot_presence(self.bot, state, None)
            return

        # Idle shutdown logic
        if player_count == 0:
            self.zero_player_minutes += 1
            logger.info(
                f"No players online. Zero-player minutes: "
                f"{self.zero_player_minutes}/{Config.IDLE_MINUTES_BEFORE_STOP}"
            )

            if self.zero_player_minutes >= Config.IDLE_MINUTES_BEFORE_STOP:
                logger.info("Idle threshold reached. Stopping the instance.")
                try:
                    self.aws_service.stop_instance()
                except Exception as e:
                    logger.error(f"Failed to stop instance: {e}")
                self.zero_player_minutes = 0
        else:
            if self.zero_player_minutes != 0:
                logger.info("Players online again. Resetting zero_player_minutes.")
            self.zero_player_minutes = 0

        # Update presence to reflect running + current players
        await update_bot_presence(self.bot, state, player_count)
