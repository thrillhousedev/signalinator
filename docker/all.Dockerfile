# Signalinator Monorepo Dockerfile
# Builds all bots from the monorepo

FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy workspace configuration
COPY pyproject.toml ./
COPY packages/ packages/
COPY bots/ bots/

# Install all packages in editable mode
RUN pip install --no-cache-dir -e packages/signalinator-core
RUN pip install --no-cache-dir -e bots/taginator
RUN pip install --no-cache-dir -e bots/informinator
RUN pip install --no-cache-dir -e bots/newsinator
RUN pip install --no-cache-dir -e bots/decisionator
RUN pip install --no-cache-dir -e bots/summarizinator
RUN pip install --no-cache-dir -e "bots/informationator[vision]"
RUN pip install --no-cache-dir -e bots/conductinator

# ==============================================================================
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlcipher1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash signalinator
USER signalinator
WORKDIR /home/signalinator

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/taginator /usr/local/bin/
COPY --from=builder /usr/local/bin/informinator /usr/local/bin/
COPY --from=builder /usr/local/bin/newsinator /usr/local/bin/
COPY --from=builder /usr/local/bin/decisionator /usr/local/bin/
COPY --from=builder /usr/local/bin/summarizinator /usr/local/bin/
COPY --from=builder /usr/local/bin/informationator /usr/local/bin/
COPY --from=builder /usr/local/bin/conductinator /usr/local/bin/

# Default environment
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Default command (override in docker-compose)
CMD ["taginator", "--help"]
