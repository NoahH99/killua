"""
AWS service module for EC2 and CloudWatch operations.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple, List

import boto3

from config import Config

logger = logging.getLogger("mc-bot.aws")


class AWSService:
    """Service for managing AWS EC2 instances and CloudWatch logs."""

    def __init__(self):
        """Initialize AWS clients."""
        self.ec2 = boto3.client("ec2", region_name=Config.AWS_REGION)
        self.logs_client = boto3.client("logs", region_name=Config.AWS_REGION)
        self.instance_id = Config.EC2_INSTANCE_ID

    def _get_instance(self) -> dict:
        """
        Get instance details from AWS.

        Returns:
            dict: Instance data from AWS API.
        """
        resp = self.ec2.describe_instances(InstanceIds=[self.instance_id])
        return resp["Reservations"][0]["Instances"][0]

    def get_instance_info(self) -> Tuple[str, Optional[datetime]]:
        """
        Get instance state and launch time.

        Returns:
            Tuple[str, Optional[datetime]]: State name and launch time.
        """
        inst = self._get_instance()
        state = inst["State"]["Name"]
        launch_time = inst.get("LaunchTime")
        return state, launch_time

    def get_instance_state(self) -> str:
        """
        Get current instance state.

        Returns:
            str: Instance state (running, stopped, pending, etc.).
        """
        state, _ = self.get_instance_info()
        return state

    def get_instance_public_ip(self) -> Optional[str]:
        """
        Get public IP address of the instance.

        Returns:
            Optional[str]: Public IP address or None.
        """
        try:
            inst = self._get_instance()
            return inst.get("PublicIpAddress")
        except Exception as e:
            logger.warning(f"Failed to get instance public IP: {e}")
            return None

    def get_rcon_host(self) -> Optional[str]:
        """
        Get RCON host (public IP or DNS) if instance is running.

        Returns:
            Optional[str]: Host address or None if not available.
        """
        try:
            inst = self._get_instance()
            state = inst["State"]["Name"]
            if state != "running":
                return None

            public_ip = inst.get("PublicIpAddress")
            public_dns = inst.get("PublicDnsName")
            host = public_ip or public_dns
            if not host:
                logger.warning("Instance is running but has no public IP/DNS")
            return host
        except Exception as e:
            logger.warning(f"Failed to get RCON host from EC2: {e}")
            return None

    def start_instance(self) -> None:
        """Start the EC2 instance."""
        logger.info(f"Starting EC2 instance {self.instance_id}")
        self.ec2.start_instances(InstanceIds=[self.instance_id])

    def stop_instance(self) -> None:
        """Stop the EC2 instance."""
        logger.info(f"Stopping EC2 instance {self.instance_id}")
        self.ec2.stop_instances(InstanceIds=[self.instance_id])

    async def wait_for_instance_running(
        self,
        poll_interval: int = 10,
        timeout: int = 600
    ) -> bool:
        """
        Wait for instance to reach running state.

        Args:
            poll_interval: Seconds between checks.
            timeout: Maximum seconds to wait.

        Returns:
            bool: True if instance is running, False if timeout.
        """
        remaining = timeout
        while remaining > 0:
            state = self.get_instance_state()
            logger.info(f"Instance state: {state}")
            if state == "running":
                return True
            await asyncio.sleep(poll_interval)
            remaining -= poll_interval
        return False

    def get_log_lines(
        self,
        direction: str,
        lines: int = 20
    ) -> Optional[List[str]]:
        """
        Get log lines from CloudWatch.

        Args:
            direction: "head" for oldest lines, "tail" for newest.
            lines: Number of lines to retrieve.

        Returns:
            Optional[List[str]]: List of log messages or None if unavailable.
        """
        if not Config.MC_CW_LOG_GROUP:
            return None

        try:
            streams = self.logs_client.describe_log_streams(
                logGroupName=Config.MC_CW_LOG_GROUP,
                orderBy="LastEventTime",
                descending=True,
                limit=1,
            )["logStreams"]

            if not streams:
                return None

            stream_name = streams[0]["logStreamName"]

            if direction == "head":
                # For head, start from the beginning
                events = self.logs_client.get_log_events(
                    logGroupName=Config.MC_CW_LOG_GROUP,
                    logStreamName=stream_name,
                    limit=lines,
                    startFromHead=True,
                )["events"]
                messages = [e["message"] for e in events]
            else:
                # For tail, fetch more events than needed and slice from the end
                # CloudWatch's limit doesn't work reliably with startFromHead=False
                fetch_limit = max(lines * 2, 100)  # Fetch extra to ensure we get enough
                events = self.logs_client.get_log_events(
                    logGroupName=Config.MC_CW_LOG_GROUP,
                    logStreamName=stream_name,
                    limit=fetch_limit,
                    startFromHead=False,
                )["events"]
                # Take the last N events (most recent) and reverse to chronological order
                messages = [e["message"] for e in events[-lines:]]

            return messages
        except Exception as e:
            logger.warning(f"Failed to fetch CloudWatch log lines: {e}")
            return None
