"""
AWS service module for EC2 and CloudWatch operations.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict

import boto3

from config import Config

logger = logging.getLogger("mc-bot.aws")


class AWSService:
    """Service for managing AWS EC2 instances and CloudWatch logs."""

    def __init__(self):
        """Initialize AWS clients."""
        self.ec2 = boto3.client("ec2", region_name=Config.AWS_REGION)
        self.logs_client = boto3.client("logs", region_name=Config.AWS_REGION)
        self.ce_client = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is always us-east-1
        self.cloudwatch = boto3.client("cloudwatch", region_name=Config.AWS_REGION)
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

    def get_monthly_costs(self) -> Optional[Dict[str, any]]:
        """
        Get AWS costs for the current month and last month.
        Includes both total account costs and Minecraft server-specific costs.

        Returns:
            Optional[Dict]: Cost data with current month, last month, and forecast,
                           or None if unavailable.
        """
        try:
            # Get the first day of current month and today
            today = datetime.now().date()
            first_of_month = today.replace(day=1)

            # Get first day of last month
            last_month_end = first_of_month - timedelta(days=1)
            first_of_last_month = last_month_end.replace(day=1)

            # Get first day of next month for forecast
            first_of_next_month = (first_of_month + timedelta(days=32)).replace(day=1)

            # ========== TOTAL ACCOUNT COSTS ==========

            # Total current month costs (month-to-date)
            total_current_response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': first_of_month.strftime('%Y-%m-%d'),
                    'End': today.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
            )

            # Total last month costs (full month)
            total_last_response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': first_of_last_month.strftime('%Y-%m-%d'),
                    'End': first_of_month.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
            )

            # Total forecast for rest of current month
            total_forecast_response = self.ce_client.get_cost_forecast(
                TimePeriod={
                    'Start': today.strftime('%Y-%m-%d'),
                    'End': first_of_next_month.strftime('%Y-%m-%d')
                },
                Metric='UNBLENDED_COST',
                Granularity='MONTHLY',
            )

            # ========== MINECRAFT SERVER COSTS (EC2 + CloudWatch) ==========

            # Get all services breakdown to see what's available
            services_current_response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': first_of_month.strftime('%Y-%m-%d'),
                    'End': today.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )

            # Parse all services to find EC2 and CloudWatch
            ec2_current = 0.0
            cw_current = 0.0
            service_breakdown = {}

            if services_current_response['ResultsByTime']:
                for group in services_current_response['ResultsByTime'][0].get('Groups', []):
                    service_name = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    service_breakdown[service_name] = cost

                    # Match EC2-related services
                    if 'Elastic Compute Cloud' in service_name or 'EC2' in service_name:
                        ec2_current += cost
                    # Match CloudWatch services
                    elif 'CloudWatch' in service_name:
                        cw_current += cost

            # Do the same for last month
            services_last_response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': first_of_last_month.strftime('%Y-%m-%d'),
                    'End': first_of_month.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )

            ec2_last = 0.0
            cw_last = 0.0

            if services_last_response['ResultsByTime']:
                for group in services_last_response['ResultsByTime'][0].get('Groups', []):
                    service_name = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])

                    if 'Elastic Compute Cloud' in service_name or 'EC2' in service_name:
                        ec2_last += cost
                    elif 'CloudWatch' in service_name:
                        cw_last += cost

            # Parse total costs
            total_current = 0.0
            if total_current_response['ResultsByTime']:
                total_current = float(
                    total_current_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
                )

            total_last = 0.0
            if total_last_response['ResultsByTime']:
                total_last = float(
                    total_last_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
                )

            total_forecast = 0.0
            if total_forecast_response['Total']:
                total_forecast = float(total_forecast_response['Total']['Amount'])

            # Calculate Minecraft server totals (EC2 + CloudWatch)
            mc_current = ec2_current + cw_current
            mc_last = ec2_last + cw_last

            # Estimate MC forecast proportionally
            if total_current > 0:
                mc_forecast = total_forecast * (mc_current / total_current)
            else:
                mc_forecast = 0.0

            return {
                # Total account costs
                'total_current': total_current,
                'total_last': total_last,
                'total_forecast': total_forecast,
                'total_projected': total_current + total_forecast,

                # Minecraft server costs (EC2 + CloudWatch)
                'mc_current': mc_current,
                'mc_last': mc_last,
                'mc_forecast': mc_forecast,
                'mc_projected': mc_current + mc_forecast,

                # Breakdown
                'ec2_current': ec2_current,
                'ec2_last': ec2_last,
                'cw_current': cw_current,
                'cw_last': cw_last,

                # Metadata
                'current_month_name': first_of_month.strftime('%B %Y'),
                'last_month_name': first_of_last_month.strftime('%B %Y'),
                'service_breakdown': service_breakdown,  # For debugging
            }

        except Exception as e:
            logger.error(f"Failed to fetch AWS costs: {e}")
            return None

    def get_performance_metrics(self, period_minutes: int = 5) -> Optional[Dict[str, any]]:
        """
        Get EC2 and CloudWatch performance metrics for the instance.

        Args:
            period_minutes: How many minutes of data to look back (default 5).

        Returns:
            Optional[Dict]: Performance metrics data or None if unavailable.
        """
        try:
            from datetime import datetime, timezone

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=period_minutes)

            # Helper function to discover dimensions for a metric
            def discover_dimensions(metric_name: str, required_dims: dict = None, prefer_patterns: list = None) -> list:
                """
                Discover the actual dimensions for a metric in CloudWatch.

                Args:
                    metric_name: The metric name to query
                    required_dims: Dict of dimension names to required values (e.g., {'path': '/'})
                    prefer_patterns: List of patterns to prefer when matching (e.g., ['xvda', 'nvme0n1'])

                Returns:
                    List of dimension dicts or empty list if not found
                """
                try:
                    list_response = self.cloudwatch.list_metrics(
                        Namespace='MinecraftServer',
                        MetricName=metric_name
                    )
                    if list_response.get('Metrics'):
                        candidates = []

                        # Collect all matching metrics
                        for metric in list_response['Metrics']:
                            dimensions = metric.get('Dimensions', [])
                            if required_dims:
                                # Check if this metric has the required dimension values
                                matches = True
                                for req_name, req_value in required_dims.items():
                                    dim_values = [d['Value'] for d in dimensions if d['Name'] == req_name]
                                    if not dim_values or dim_values[0] != req_value:
                                        matches = False
                                        break
                                if matches:
                                    candidates.append(dimensions)
                            else:
                                candidates.append(dimensions)

                        # If we have preferred patterns, try to find the best match
                        if candidates and prefer_patterns:
                            for pattern in prefer_patterns:
                                for dims in candidates:
                                    # Check if any dimension value contains the pattern
                                    for dim in dims:
                                        if pattern in dim['Value']:
                                            return dims

                        # Return first candidate if no pattern match
                        if candidates:
                            return candidates[0]

                except Exception as e:
                    logger.warning(f"Failed to discover dimensions for {metric_name}: {e}")
                return []

            # Discover hostname
            hostname = None
            cpu_dims = discover_dimensions('cpu_usage_idle')
            if cpu_dims:
                for dim in cpu_dims:
                    if dim['Name'] == 'host':
                        hostname = dim['Value']
                        logger.info(f"Discovered hostname for metrics: {hostname}")
                        break

            metrics_to_fetch = {
                # Built-in EC2 metrics (always available)
                'ec2': {
                    'namespace': 'AWS/EC2',
                    'metrics': [
                        {'name': 'CPUUtilization', 'stat': 'Average', 'unit': 'Percent'},
                        {'name': 'NetworkIn', 'stat': 'Sum', 'unit': 'Bytes'},
                        {'name': 'NetworkOut', 'stat': 'Sum', 'unit': 'Bytes'},
                        {'name': 'StatusCheckFailed', 'stat': 'Maximum', 'unit': 'Count'},
                    ],
                    'dimensions': [{'Name': 'InstanceId', 'Value': self.instance_id}]
                },
                # Custom CloudWatch Agent metrics (use hostname dimension if available)
                'custom': {
                    'namespace': 'MinecraftServer',
                    'metrics': [
                        # CPU metrics (discover all dimensions)
                        {'name': 'cpu_usage_user', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('cpu_usage_user', {'host': hostname, 'cpu': 'cpu-total'}) if hostname else []},
                        {'name': 'cpu_usage_system', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('cpu_usage_system', {'host': hostname, 'cpu': 'cpu-total'}) if hostname else []},
                        {'name': 'cpu_usage_idle', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('cpu_usage_idle', {'host': hostname, 'cpu': 'cpu-total'}) if hostname else []},
                        {'name': 'cpu_usage_iowait', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('cpu_usage_iowait', {'host': hostname, 'cpu': 'cpu-total'}) if hostname else []},

                        # Memory metrics (need host dimension only)
                        {'name': 'mem_used_percent', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('mem_used_percent', {'host': hostname}) if hostname else []},
                        {'name': 'mem_available', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('mem_available', {'host': hostname}) if hostname else []},
                        {'name': 'mem_used', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('mem_used', {'host': hostname}) if hostname else []},
                        {'name': 'mem_total', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('mem_total', {'host': hostname}) if hostname else []},

                        # Disk usage metrics (discover all dimensions for root filesystem)
                        {'name': 'disk_used_percent', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('disk_used_percent', {'path': '/'}) if hostname else []},
                        {'name': 'disk_free', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('disk_free', {'path': '/'}) if hostname else []},

                        # Disk I/O metrics (discover dimensions for primary disk device)
                        # Prefer xvda/nvme0n1 over loop devices
                        {'name': 'diskio_read_bytes', 'stat': 'Sum', 'unit': 'None',
                         'dimensions': discover_dimensions('diskio_read_bytes', {'host': hostname}, prefer_patterns=['xvda', 'nvme0n1', 'sda']) if hostname else []},
                        {'name': 'diskio_write_bytes', 'stat': 'Sum', 'unit': 'None',
                         'dimensions': discover_dimensions('diskio_write_bytes', {'host': hostname}, prefer_patterns=['xvda', 'nvme0n1', 'sda']) if hostname else []},
                        {'name': 'diskio_reads', 'stat': 'Sum', 'unit': 'None',
                         'dimensions': discover_dimensions('diskio_reads', {'host': hostname}, prefer_patterns=['xvda', 'nvme0n1', 'sda']) if hostname else []},
                        {'name': 'diskio_writes', 'stat': 'Sum', 'unit': 'None',
                         'dimensions': discover_dimensions('diskio_writes', {'host': hostname}, prefer_patterns=['xvda', 'nvme0n1', 'sda']) if hostname else []},

                        # Network metrics (discover all dimensions)
                        {'name': 'net_bytes_sent', 'stat': 'Sum', 'unit': 'None',
                         'dimensions': discover_dimensions('net_bytes_sent', {'host': hostname, 'interface': 'enX0'}) if hostname else []},
                        {'name': 'net_bytes_recv', 'stat': 'Sum', 'unit': 'None',
                         'dimensions': discover_dimensions('net_bytes_recv', {'host': hostname, 'interface': 'enX0'}) if hostname else []},

                        # Connection metrics (discover all dimensions)
                        {'name': 'netstat_tcp_established', 'stat': 'Average', 'unit': 'None',
                         'dimensions': discover_dimensions('netstat_tcp_established', {'host': hostname}) if hostname else []},
                    ]
                }
            }

            results = {}

            # Fetch metrics
            for category, config in metrics_to_fetch.items():
                results[category] = {}
                for metric_info in config['metrics']:
                    try:
                        # Use metric-specific dimensions if provided, otherwise use config dimensions
                        dimensions = metric_info.get('dimensions', config.get('dimensions', []))

                        # Log dimensions for debugging
                        if not dimensions:
                            logger.warning(f"No dimensions found for {metric_info['name']}")
                        else:
                            logger.debug(f"Querying {metric_info['name']} with {len(dimensions)} dimensions")

                        # Build query params
                        query_params = {
                            'Namespace': config['namespace'],
                            'MetricName': metric_info['name'],
                            'Dimensions': dimensions,
                            'StartTime': start_time,
                            'EndTime': end_time,
                            'Period': 60,  # 1 minute granularity
                            'Statistics': [metric_info['stat']]
                        }

                        # Only add Unit if it's not 'None' (custom metrics don't have units)
                        if metric_info['unit'] != 'None':
                            query_params['Unit'] = metric_info['unit']

                        response = self.cloudwatch.get_metric_statistics(**query_params)

                        datapoints = response.get('Datapoints', [])
                        if datapoints:
                            # Sort by timestamp and get the latest value
                            datapoints.sort(key=lambda x: x['Timestamp'], reverse=True)
                            latest = datapoints[0]
                            results[category][metric_info['name']] = {
                                'value': latest.get(metric_info['stat'], 0),
                                'timestamp': latest['Timestamp'],
                                'unit': metric_info['unit']
                            }

                            # Also calculate average over period
                            avg_value = sum(dp.get(metric_info['stat'], 0) for dp in datapoints) / len(datapoints)
                            results[category][metric_info['name']]['average'] = avg_value
                            logger.debug(f"✓ {metric_info['name']}: {results[category][metric_info['name']]['value']}")
                        else:
                            logger.warning(f"No datapoints returned for {metric_info['name']} (dims: {len(dimensions)})")
                            results[category][metric_info['name']] = None

                    except Exception as e:
                        logger.warning(f"Failed to fetch {metric_info['name']}: {e}")
                        results[category][metric_info['name']] = None

            # Get instance type for context
            instance_info = self._get_instance()
            instance_type = instance_info.get('InstanceType', 'unknown')

            return {
                'instance_id': self.instance_id,
                'instance_type': instance_type,
                'metrics': results,
                'period_minutes': period_minutes,
                'timestamp': end_time
            }

        except Exception as e:
            logger.error(f"Failed to fetch performance metrics: {e}")
            return None

    def list_available_metrics(self, namespace: str = 'MinecraftServer') -> List[Dict]:
        """
        List all available metrics in a CloudWatch namespace.

        Args:
            namespace: The CloudWatch namespace to query (default: MinecraftServer).

        Returns:
            List of metric information dictionaries.
        """
        try:
            response = self.cloudwatch.list_metrics(Namespace=namespace)
            return response.get('Metrics', [])
        except Exception as e:
            logger.error(f"Failed to list metrics: {e}")
            return []
