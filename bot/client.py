"""
Discord bot client setup and initialization.
"""
import logging

import discord
from discord import app_commands

from config import Config
from services.aws import AWSService
from services.rcon import RCONService
from services.cloudflare import CloudflareService
from bot.tasks import BotTasks
from commands.server import create_server_commands
from commands.status import create_status_commands
from commands.admin import create_admin_commands
from commands.chat import create_chat_commands
from utils.discord_helpers import update_bot_presence

logger = logging.getLogger("mc-bot.client")


class MinecraftBot:
    """Main bot class that orchestrates all components."""

    def __init__(self):
        """Initialize the Minecraft Discord bot."""
        # Setup Discord client
        intents = discord.Intents.default()
        self.bot = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.bot)

        # Initialize services
        self.aws_service = AWSService()
        self.rcon_service = RCONService(self.aws_service)
        self.cloudflare_service = CloudflareService()

        # Initialize background tasks
        self.bot_tasks = BotTasks(
            self.bot,
            self.aws_service,
            self.rcon_service,
        )

        # Setup command group
        self.mc_group = app_commands.Group(
            name="mc",
            description="Minecraft server controls"
        )

        # Register commands
        self._register_commands()

        # Register event handlers
        self._register_events()

    def _register_commands(self) -> None:
        """Register all command groups."""
        # Server control commands
        create_server_commands(
            self.mc_group,
            self.aws_service,
            self.rcon_service,
            self.cloudflare_service,
        )

        # Status commands
        create_status_commands(
            self.mc_group,
            self.aws_service,
            self.rcon_service,
            lambda: self.bot_tasks,  # Pass getter for task state
        )

        # Admin commands
        create_admin_commands(
            self.mc_group,
            self.aws_service,
            self.rcon_service,
            lambda: self.bot_tasks,  # Pass getter for task state
        )

        # Chat commands
        create_chat_commands(
            self.mc_group,
            self.rcon_service,
        )

        # Add command group to tree
        self.tree.add_command(self.mc_group)

    def _register_events(self) -> None:
        """Register Discord event handlers."""

        @self.bot.event
        async def on_ready():
            """Called when the bot is ready."""
            logger.info(f"Logged in as {self.bot.user} (ID: {self.bot.user.id})")

            # Sync slash commands
            await self.tree.sync()
            logger.info("Slash commands synced.")

            # Start background tasks
            self.bot_tasks.start()

            # Set initial presence
            try:
                state, _ = self.aws_service.get_instance_info()
                await update_bot_presence(self.bot, state, None)
            except Exception as e:
                logger.warning(f"Could not set initial presence: {e}")

    def run(self) -> None:
        """
        Start the bot.

        Validates configuration and starts the Discord client.
        """
        # Validate configuration
        Config.validate()

        # Run the bot
        logger.info("Starting Minecraft Discord bot...")
        self.bot.run(Config.DISCORD_TOKEN)
