"""
Configuration module for the Minecraft Discord Bot.
Loads and validates environment variables.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Central configuration management using environment variables."""

    # Discord Configuration
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN")
    ADMIN_DISCORD_ID: int = int(os.getenv("ADMIN_DISCORD_ID", "0"))

    # AWS Configuration
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    EC2_INSTANCE_ID: str = os.getenv("EC2_INSTANCE_ID")
    MC_CW_LOG_GROUP: str = os.getenv("MC_CW_LOG_GROUP", "minecraft-server")

    # RCON Configuration
    RCON_PORT: int = int(os.getenv("RCON_PORT", "25575"))
    RCON_PASSWORD: str = os.getenv("RCON_PASSWORD")

    # Cloudflare Configuration (Optional)
    CLOUDFLARE_API_TOKEN: Optional[str] = os.getenv("CLOUDFLARE_API_TOKEN")
    CF_ZONE_ID: Optional[str] = os.getenv("CF_ZONE_ID")
    CF_DNS_RECORD_NAME: Optional[str] = os.getenv("CF_DNS_RECORD_NAME")

    # Server Management
    IDLE_MINUTES_BEFORE_STOP: int = int(os.getenv("IDLE_MINUTES_BEFORE_STOP", "5"))

    @classmethod
    def validate(cls) -> None:
        """
        Validate that all required configuration values are present.

        Raises:
            ValueError: If any required configuration is missing.
        """
        required_vars = {
            "DISCORD_TOKEN": cls.DISCORD_TOKEN,
            "EC2_INSTANCE_ID": cls.EC2_INSTANCE_ID,
            "RCON_PASSWORD": cls.RCON_PASSWORD,
            "ADMIN_DISCORD_ID": cls.ADMIN_DISCORD_ID,
        }

        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                "Please set them in your .env file or environment."
            )

    @classmethod
    def has_cloudflare_config(cls) -> bool:
        """Check if Cloudflare configuration is complete."""
        return all([
            cls.CLOUDFLARE_API_TOKEN,
            cls.CF_ZONE_ID,
            cls.CF_DNS_RECORD_NAME,
        ])
