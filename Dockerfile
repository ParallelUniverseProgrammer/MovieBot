# syntax=docker/dockerfile:1

# Multi-stage build to keep runtime image slim
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (add git/curl if needed). tzdata for timezones; build-essential for some wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential \
    tzdata \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better caching
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# Copy the rest of the code
COPY . .

# Note: run as root to avoid Windows bind mount permission issues
# If you prefer non-root, uncomment below and adjust volume ownership accordingly
# RUN useradd -m bot && chown -R bot:bot /app
# USER bot

# Expose no ports (Discord connects outbound). Compose may still define a network.

# Default envs (can be overridden via docker run / compose)
ENV MOVIEBOT_LOG_LEVEL=INFO \
    PYTHONPATH=/app

# Ensure config directory exists (mounted in compose)
RUN mkdir -p /app/config /app/data

# Healthcheck: verify Python can import and basic script responds
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD python -c "import sys; import importlib; importlib.import_module('bot.discord_bot'); sys.exit(0)" || exit 1

# Start the Discord bot
CMD ["python", "-m", "bot.discord_bot"]


