"""
RCON service module for Minecraft server communication.
"""
import asyncio
import logging
import re
from concurrent.futures import ProcessPoolExecutor
from typing import Optional, Tuple, List

from mcrcon import MCRcon

from config import Config
from services.aws import AWSService

logger = logging.getLogger("mc-bot.rcon")

# Global process pool executor for RCON calls
# Use process pool to avoid signal issues with threading
_rcon_executor = ProcessPoolExecutor(max_workers=2)


def _execute_rcon_command(
    host: str,
    password: str,
    port: int,
    cmd: str
) -> Tuple[bool, Optional[str]]:
    """
    Execute RCON command in a separate process.
    This function must be at module level to be picklable for ProcessPoolExecutor.

    Args:
        host: RCON host address.
        password: RCON password.
        port: RCON port.
        cmd: Command to execute.

    Returns:
        Tuple[bool, Optional[str]]: Success status and response.
    """
    try:
        with MCRcon(host, password, port=port) as mcr:
            return True, mcr.command(cmd)
    except Exception as e:
        # Logger won't work across processes, so we just return the error
        return False, None


class RCONService:
    """Service for managing Minecraft RCON connections."""

    def __init__(self, aws_service: AWSService):
        """
        Initialize RCON service.

        Args:
            aws_service: AWS service instance for getting host information.
        """
        self.aws_service = aws_service
        self.port = Config.RCON_PORT
        self.password = Config.RCON_PASSWORD

    async def execute_command(self, cmd: str) -> Tuple[bool, Optional[str]]:
        """
        Execute a command via RCON.

        Args:
            cmd: Command to execute.

        Returns:
            Tuple[bool, Optional[str]]: Success status and response.
        """
        host = self.aws_service.get_rcon_host()
        if not host:
            logger.warning("RCON host is not available (instance not running or no public IP)")
            return False, None

        loop = asyncio.get_running_loop()

        # Run in process pool to avoid signal issues
        ok, resp = await loop.run_in_executor(
            _rcon_executor,
            _execute_rcon_command,
            host,
            self.password,
            self.port,
            cmd
        )
        if ok:
            logger.info(f"RCON '{cmd}' response: {resp}")
        return ok, resp

    async def is_reachable(self) -> bool:
        """
        Check if RCON is reachable.

        Returns:
            bool: True if RCON responds, False otherwise.
        """
        ok, _ = await self.execute_command("list")
        return ok

    async def get_player_info(self) -> Optional[Tuple[int, List[str]]]:
        """
        Get player count and names.

        Returns:
            Optional[Tuple[int, List[str]]]: Player count and list of names, or None.
        """
        ok, resp = await self.execute_command("list")
        if not ok or resp is None:
            return None

        try:
            parts = resp.split()
            count = int(parts[2])
        except Exception:
            logger.warning(f"Could not parse player count from: {resp}")
            return None

        names = []
        if ":" in resp:
            after_colon = resp.split(":", 1)[1].strip()
            if after_colon:
                names = [n.strip() for n in after_colon.split(",") if n.strip()]

        return count, names

    async def get_player_count(self) -> Optional[int]:
        """
        Get current player count.

        Returns:
            Optional[int]: Number of players online, or None.
        """
        info = await self.get_player_info()
        if info is None:
            return None
        count, _ = info
        return count

    async def get_tps(self) -> Optional[Tuple[float, float, float]]:
        """
        Get TPS (ticks per second) for Paper servers.

        Returns:
            Optional[Tuple[float, float, float]]: TPS for 1m, 5m, 15m or None.
        """
        ok, resp = await self.execute_command("tps")
        if not ok or resp is None:
            return None

        nums = re.findall(r"(\d+\.\d+|\d+)", resp)
        if len(nums) >= 3:
            try:
                return float(nums[0]), float(nums[1]), float(nums[2])
            except ValueError:
                pass
        logger.warning(f"Could not parse TPS from: {resp}")
        return None

    async def get_paper_version(
        self,
        poll_interval: int = 3,
        timeout: int = 60,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Poll RCON for Paper version until available or timeout.

        Args:
            poll_interval: Seconds between polls.
            timeout: Maximum seconds to wait.

        Returns:
            Tuple[Optional[str], Optional[str]]: Short version and full version, or (None, None).
        """
        remaining = timeout

        while remaining > 0:
            ok, resp = await self.execute_command("version")
            if not ok or not resp:
                logger.info("get_paper_version: RCON not ready or empty response, retrying...")
            else:
                # Strip MC formatting codes like §f, §o, §a, §r...
                clean = re.sub(r"§.", "", resp)

                # Paper startup placeholder
                if "Checking version, please wait" not in clean:
                    # We have a real version response
                    lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
                    full_version = lines[0] if lines else clean.strip()

                    # 1) Old style: "MC: 1.21.1"
                    m = re.search(r"MC:\s*([0-9.]+)", clean)
                    if not m:
                        # 2) Your style: "Paper version 1.21.10-113-main@..."
                        m = re.search(r"version\s+([0-9]+\.[0-9.]+)", clean, re.IGNORECASE)

                    short_version = m.group(1) if m else None

                    logger.info(f"Parsed Paper version: short={short_version}, full={full_version}")
                    return short_version, full_version

                logger.info("get_paper_version: still got 'Checking version, please wait', retrying...")

            await asyncio.sleep(poll_interval)
            remaining -= poll_interval

        logger.warning("get_paper_version: timed out waiting for Paper version.")
        return None, None

    async def wait_for_ready(
        self,
        poll_interval: int = 5,
        timeout: int = 120
    ) -> bool:
        """
        Wait for RCON to become ready.

        Args:
            poll_interval: Seconds between checks.
            timeout: Maximum seconds to wait.

        Returns:
            bool: True if RCON is ready, False if timeout.
        """
        remaining = timeout
        while remaining > 0:
            if await self.is_reachable():
                logger.info("RCON is now reachable.")
                return True

            logger.info(f"RCON not ready yet, retrying in {poll_interval} seconds...")
            await asyncio.sleep(poll_interval)
            remaining -= poll_interval

        logger.warning(f"RCON did not become ready within {timeout} seconds.")
        return False
