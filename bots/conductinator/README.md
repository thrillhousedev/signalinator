# Conductinator

Signal bot for managing other Signalinator bot containers via Docker.

Conductinator allows authorized admins to start, stop, restart, and monitor other bots in the Signalinator ecosystem through Signal direct messages.

## Features

- **Bot Management**: Start, stop, restart any Signalinator bot
- **Log Viewing**: View recent logs from bots and their signal daemons
- **Status Overview**: See all bots and their running status
- **Audit Log**: Track all management actions
- **Health Check**: Verify Docker connection and bot status
- **DM-Only**: All commands require direct message (no group commands)
- **Admin Whitelist**: Only authorized UUIDs can execute commands

## Commands

All commands are DM-only and require admin authorization.

| Command | Description |
|---------|-------------|
| `/status` | Show all bot statuses |
| `/start <bot>` | Start a stopped bot |
| `/stop <bot>` | Stop a running bot |
| `/restart <bot>` | Restart a bot |
| `/logs <bot> [lines]` | View recent bot logs (default: 30, max: 100) |
| `/daemon-logs <bot> [lines]` | View signal daemon logs |
| `/audit [lines]` | View recent audit log (default: 20, max: 50) |
| `/health` | Check Docker connection health |
| `/help` | Show available commands |

## Usage Examples

```
/status
→ Bot Status:
  🟢 taginator: running
  🔴 newsinator: stopped
  🟢 informinator: running

/start newsinator
→ ✅ Started newsinator

/logs taginator 50
→ Logs for taginator (last 50 lines):
  [log output...]

/health
→ System Health:
  Docker: ✅ connected
  Bots found: 6
  Bots running: 4
```

## Configuration

| Variable | Description |
|----------|-------------|
| `CONDUCTINATOR_ADMINS` | Comma-separated UUIDs allowed to use commands |
| `DOCKER_SOCKET` | Path to Docker socket (default: `/var/run/docker.sock`) |

## Security

- **Admin Whitelist**: Only UUIDs listed in `CONDUCTINATOR_ADMINS` can execute commands
- **DM-Only**: Commands are ignored in groups
- **Audit Trail**: All actions are logged with timestamp and admin UUID
- **Self-Protection**: Cannot stop conductinator from within conductinator

## Docker Socket Access

Conductinator requires access to the Docker socket to manage containers. In the docker-compose configuration, this is mounted as read-only:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

## Known Bots

Conductinator recognizes these Signalinator bots:
- conductinator
- decisionator
- informationator
- informinator
- newsinator
- summarizinator
- taginator
