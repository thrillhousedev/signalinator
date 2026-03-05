# signal-cli daemon for signalinator bots
# Note: signal-cli native binary is x86_64 only - use platform: linux/amd64 in docker-compose
FROM python:3.11-slim

# Install dependencies for signal-cli and setup wizard
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install signal-cli native binary
ARG SIGNAL_CLI_VERSION=0.13.21
RUN wget -q https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz \
    && tar xf signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz -C /opt \
    && chmod +x /opt/signal-cli \
    && ln -sf /opt/signal-cli /usr/local/bin/signal-cli \
    && rm signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz

# Install signalinator-core for SetupWizard
WORKDIR /app
COPY packages/signalinator-core /app/packages/signalinator-core
RUN pip install --no-cache-dir /app/packages/signalinator-core

# Copy entrypoint and setup scripts (755 for non-root user execution)
COPY docker/scripts/signal-entrypoint.sh /signal-entrypoint.sh
COPY docker/scripts/signal-setup.py /app/signal-setup.py
RUN chmod 755 /signal-entrypoint.sh /app/signal-setup.py

# Create user and config directory
RUN useradd -m -u 1000 signal \
    && mkdir -p /signal-cli-config \
    && chown -R signal:signal /signal-cli-config /app

USER signal
EXPOSE 8080

# Smart entrypoint handles: daemon mode, setup, link, status
ENTRYPOINT ["/signal-entrypoint.sh"]
