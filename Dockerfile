# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and create user in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -u 1000 botuser

# Copy requirements first for better layer caching
# Use --chown to set ownership directly, avoiding extra chown layer
COPY --chown=botuser:botuser requirements.txt .

# Switch to non-root user before installing dependencies
USER botuser

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code in a single layer for better caching
# If any app file changes, only this layer and subsequent ones rebuild
COPY --chown=botuser:botuser . .

# Run the bot
CMD ["python", "-u", "main.py"]
