# Transcribinator

Audio/video transcription bot using local Whisper with optional AI cleanup and summarization.

## Features

- Transcribes audio and video files sent via Signal using [OpenAI Whisper](https://github.com/openai/whisper) (runs locally, no cloud API)
- Optional AI-powered cleanup that fixes transcription errors without changing meaning
- Optional quick summary of the transcribed content
- Supports voice notes, audio files, and video files
- Fully containerized -- Whisper runs inside the Docker container

## Usage

### In Groups
Mention the bot with an audio/video attachment:
- `@transcribinator` + audio file -- raw transcription
- `/clean` + audio file -- transcription + AI-cleaned version
- `/summary` + audio file -- transcription + quick summary
- `/full` + audio file -- transcription + cleaned + summary

### In DMs
Just send an audio/video file directly. Use `/clean`, `/summary`, or `/full` for AI features.

### Commands
| Command | Description |
|---------|-------------|
| `/clean` | Transcribe + AI-cleaned version |
| `/summary` | Transcribe + quick summary |
| `/full` | Transcribe + cleaned + summary |
| `/status` | Show Whisper, ffmpeg, and Ollama status |
| `/help` | Show usage information |

## Supported Formats

### Audio
AAC, MP3, M4A, WAV, WebM, OGG, AMR, FLAC

### Video (audio track extracted)
MP4, WebM, QuickTime (.mov), 3GPP

## Whisper Models

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny | 39 MB | Fastest | Basic |
| base | 74 MB | Fast | Good (default) |
| small | 244 MB | Moderate | Better |
| medium | 769 MB | Slow | Great |
| large | 1.5 GB | Slowest | Best |

Set via `WHISPER_MODEL` environment variable.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TRANSCRIBINATOR_PHONE` | Signal phone number | Required |
| `TRANSCRIBINATOR_DAEMON_PORT` | Signal daemon port | 8089 |
| `WHISPER_MODEL` | Whisper model size | base |
| `WHISPER_MODEL_DIR` | Model cache directory | /data/whisper-models |
| `OLLAMA_HOST` | Ollama server URL | http://localhost:11434 |
| `TRANSCRIBINATOR_OLLAMA_MODEL` | Override Ollama model | (uses OLLAMA_MODEL) |

## Development

```bash
# Install in development mode
pip install -e packages/signalinator-core
pip install -e bots/transcribinator

# Run tests
pytest bots/transcribinator/tests/ -v

# Run locally
transcribinator daemon --phone +1234567890 --db-path ./data/transcribinator.db
```

## Docker

```bash
# Build
docker compose --profile transcribinator build

# Run
docker compose --profile transcribinator up -d

# Setup Signal account
docker compose run --rm transcribinator-daemon setup
```

## Dependencies

- **Whisper** (openai-whisper) -- local speech-to-text
- **ffmpeg** -- audio/video format conversion
- **Ollama** (optional) -- AI cleanup and summarization
