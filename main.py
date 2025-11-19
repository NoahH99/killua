"""
Minecraft Discord Bot - Main Entry Point

A Discord bot for managing a Minecraft server running on AWS EC2 with
automatic idle shutdown, RCON integration, and Cloudflare DNS management.
"""
import logging

from bot.client import MinecraftBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("mc-bot")


def main():
    """Main entry point for the bot."""
    try:
        bot = MinecraftBot()
        bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
