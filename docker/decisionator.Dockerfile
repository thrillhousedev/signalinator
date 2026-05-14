# Decisionator - Loomio integration for group decisions
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY packages/ packages/
COPY bots/decisionator/ bots/decisionator/

RUN pip install --no-cache-dir packages/signalinator-core \
    && pip install --no-cache-dir pysqlcipher3 \
    && pip install --no-cache-dir bots/decisionator

# ==============================================================================
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlcipher1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash signalinator
USER signalinator
WORKDIR /home/signalinator

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/decisionator /usr/local/bin/

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

CMD ["decisionator", "daemon"]
