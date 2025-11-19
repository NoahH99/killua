# Minecraft Discord Bot

A Discord bot for managing a Minecraft server running on AWS EC2 with automatic idle shutdown, RCON integration, and Cloudflare DNS management.

## Features

- Start/stop/restart EC2 instance hosting your Minecraft server
- Automatic server shutdown after idle period (configurable)
- Real-time player count monitoring
- RCON command execution
- Discord presence showing server status and player count
- Cloudflare DNS automatic updates
- CloudWatch logs integration
- Server diagnostics and TPS monitoring
- Player management (OP/DEOP)

## Prerequisites

- Python 3.11 or higher (for local deployment)
- Docker and Docker Compose (for containerized deployment)
- AWS account with EC2 instance running Minecraft
- AWS credentials with permissions to:
  - Start/stop EC2 instances
  - Read CloudWatch logs
- Discord bot token
- Minecraft server with RCON enabled
- (Optional) Cloudflare API token for DNS management

## Installation

### Option 1: Docker Deployment (Recommended)

1. Clone or download this repository

2. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and fill in your credentials:
   ```bash
   nano .env  # or use your preferred editor
   ```

4. Build and run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

5. View logs:
   ```bash
   docker-compose logs -f minecraft-bot
   ```

6. Stop the bot:
   ```bash
   docker-compose down
   ```

### Option 2: Local Python Deployment

1. Clone or download this repository

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your credentials.

5. Run the bot:
   ```bash
   python main.py
   ```

## Configuration

### Required Environment Variables

- `DISCORD_TOKEN`: Your Discord bot token
- `EC2_INSTANCE_ID`: AWS EC2 instance ID (e.g., i-0a6d6419ff9b407e7)
- `RCON_PASSWORD`: Minecraft RCON password
- `ADMIN_DISCORD_ID`: Your Discord user ID for admin commands

### Optional Environment Variables

- `AWS_REGION`: AWS region (default: us-east-1)
- `RCON_PORT`: RCON port (default: 25575)
- `IDLE_MINUTES_BEFORE_STOP`: Minutes of inactivity before auto-shutdown (default: 5)
- `MC_CW_LOG_GROUP`: CloudWatch log group name (default: minecraft-server)
- `CLOUDFLARE_API_TOKEN`: Cloudflare API token for DNS updates
- `CF_ZONE_ID`: Cloudflare zone ID
- `CF_DNS_RECORD_NAME`: DNS record to update (e.g., mc.yourdomain.com)

### AWS Credentials

The bot uses boto3 to interact with AWS. Configure credentials using one of these methods:

1. **Environment variables**: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
2. **AWS credentials file**: `~/.aws/credentials`
3. **IAM role** (recommended for EC2/ECS deployment)

## Discord Bot Setup

1. Create a new application at https://discord.com/developers/applications
2. Go to the "Bot" section and create a bot
3. Copy the bot token to your `.env` file
4. Enable required intents:
   - Presence Intent
   - Server Members Intent (if needed)
   - Message Content Intent (if needed)
5. Invite the bot to your server using OAuth2 URL generator with:
   - `bot` and `applications.commands` scopes
   - Required permissions: Send Messages, Embed Links, Use Slash Commands

## Available Commands

All commands are under the `/mc` group:

- `/mc start` - Start the Minecraft server
- `/mc stop` - Schedule server shutdown in 1 minute
- `/mc restart` - Restart the server
- `/mc status` - Show server status, players, and uptime
- `/mc players` - List online players
- `/mc tps` - Show server TPS (Paper only)
- `/mc uptime` - Show server uptime
- `/mc say <message>` - Broadcast message in-game (admin only)
- `/mc exec <command>` - Execute raw RCON command (admin only)
- `/mc op <player>` - Grant operator status (admin only)
- `/mc deop <player>` - Remove operator status (admin only)
- `/mc logs` - View CloudWatch logs (admin only)
- `/mc diag` - Detailed diagnostics (admin only)

## Security Notes

- Never commit your `.env` file to version control
- The `.gitignore` file is configured to prevent this
- Admin commands are restricted to the Discord user ID specified in `ADMIN_DISCORD_ID`
- Use IAM roles with minimal required permissions for AWS access
- Rotate your Discord bot token and RCON password regularly

## Troubleshooting

### Bot doesn't start
- Check that all required environment variables are set
- Verify your Discord token is valid
- Check AWS credentials are configured correctly

### RCON connection fails
- Ensure RCON is enabled in `server.properties`
- Verify `RCON_PASSWORD` matches the server configuration
- Check security groups allow RCON port access from your bot's IP

### AWS permissions errors
- Verify IAM user/role has EC2 start/stop permissions
- For CloudWatch logs, ensure read permissions on the log group

### Cloudflare DNS not updating
- Verify API token has DNS edit permissions
- Check zone ID and DNS record name are correct

## License

This project is provided as-is for personal use.

## Contributing

Feel free to submit issues and pull requests for improvements.
