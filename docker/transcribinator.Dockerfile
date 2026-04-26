# Transcribinator - Audio/Video Transcription (requires Whisper + ffmpeg)
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlcipher-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY packages/ packages/
COPY bots/transcribinator/ bots/transcribinator/

RUN pip install --no-cache-dir "packages/signalinator-core[encryption]" \
    && pip install --no-cache-dir bots/transcribinator

# ==============================================================================
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlcipher1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash signalinator
USER signalinator
WORKDIR /home/signalinator

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/transcribinator /usr/local/bin/

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

CMD ["transcribinator", "daemon"]
