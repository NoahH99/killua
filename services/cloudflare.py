"""
Cloudflare service module for DNS management.
"""
import logging
from typing import Tuple, Optional

import requests

from config import Config

logger = logging.getLogger("mc-bot.cloudflare")


class CloudflareService:
    """Service for managing Cloudflare DNS records."""

    def __init__(self):
        """Initialize Cloudflare service."""
        self.api_token = Config.CLOUDFLARE_API_TOKEN
        self.zone_id = Config.CF_ZONE_ID
        self.dns_record_name = Config.CF_DNS_RECORD_NAME
        self.enabled = Config.has_cloudflare_config()

    def _get_headers(self) -> dict:
        """Get HTTP headers for Cloudflare API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _get_record_id(self) -> Optional[str]:
        """
        Get DNS record ID from Cloudflare.

        Returns:
            Optional[str]: Record ID or None if not found.
        """
        if not self.enabled:
            return None

        try:
            list_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
            params = {"type": "A", "name": self.dns_record_name}
            resp = requests.get(
                list_url,
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            data = resp.json()

            if not data.get("success"):
                logger.warning(f"Cloudflare list DNS failed: {data}")
                return None

            results = data.get("result", [])
            if not results:
                logger.warning(f"Cloudflare: no A record found for {self.dns_record_name}")
                return None

            return results[0]["id"]
        except Exception as e:
            logger.warning(f"Error looking up Cloudflare DNS record: {e}")
            return None

    def update_a_record(self, ip: str) -> Tuple[bool, str]:
        """
        Update A record to point to the given IP.

        Args:
            ip: IP address to set.

        Returns:
            Tuple[bool, str]: Success status and message.
        """
        if not self.enabled:
            msg = "Cloudflare env vars not fully set; skipping DNS update."
            logger.info(msg)
            return False, msg

        record_id = self._get_record_id()
        if not record_id:
            msg = f"Could not find DNS record {self.dns_record_name}"
            return False, msg

        try:
            # Get current record details first
            list_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
            params = {"type": "A", "name": self.dns_record_name}
            resp = requests.get(
                list_url,
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            data = resp.json()
            record = data.get("result", [{}])[0]

            # Update the record
            update_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records/{record_id}"
            payload = {
                "type": "A",
                "name": self.dns_record_name,
                "content": ip,
                "ttl": record.get("ttl", 120) or 120,
                "proxied": record.get("proxied", False),
            }

            resp = requests.put(
                update_url,
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )
            data = resp.json()
            if not data.get("success"):
                msg = f"Cloudflare update DNS failed: {data}"
                logger.warning(msg)
                return False, msg

            msg = f"Cloudflare A record {self.dns_record_name} updated to {ip}"
            logger.info(msg)
            return True, msg
        except Exception as e:
            msg = f"Error updating Cloudflare DNS record: {e}"
            logger.warning(msg)
            return False, msg

    def record_points_to_ip(self, ip: str) -> Tuple[bool, Optional[str]]:
        """
        Check if DNS record currently points to the given IP.

        Args:
            ip: IP address to check.

        Returns:
            Tuple[bool, Optional[str]]: Match status and current IP.
        """
        if not self.enabled:
            return False, None

        try:
            list_url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
            params = {"type": "A", "name": self.dns_record_name}
            resp = requests.get(
                list_url,
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            data = resp.json()

            if not data.get("success"):
                logger.warning(f"Cloudflare record check failed: {data}")
                return False, None

            results = data.get("result", [])
            if not results:
                logger.warning(f"Cloudflare record check: no A record found for {self.dns_record_name}")
                return False, None

            record = results[0]
            current = record.get("content")
            return current == ip, current
        except Exception as e:
            logger.warning(f"Error checking Cloudflare record content: {e}")
            return False, None
