# Conductinator - Manage other bot containers via Signal
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY packages/ packages/
COPY bots/conductinator/ bots/conductinator/

RUN pip install --no-cache-dir packages/signalinator-core \
    && pip install --no-cache-dir bots/conductinator

# ==============================================================================
FROM python:3.11-slim

# Install runtime dependencies plus docker CLI for docker compose commands
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlcipher1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (needed for docker compose commands)
RUN curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash signalinator
# Note: We run as root in docker-compose.yml to access Docker socket
WORKDIR /home/signalinator

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/conductinator /usr/local/bin/

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

CMD ["conductinator", "daemon"]
