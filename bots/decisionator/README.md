# Decisionator

Privacy-focused group decision-making via Signal, integrated with Loomio.

Decisionator connects your Signal groups to a Loomio instance, allowing members to create polls, vote, and discuss decisions without leaving Signal.

## Features

- **Poll Creation**: Proposals, polls, score polls, ranked choice, meeting schedulers
- **Voting**: Vote via Signal with optional reasons
- **Auto-Announce**: Automatic result announcements when polls close
- **Discussion**: Add comments to polls from Signal
- **Admin Tools**: Close, extend, reopen polls; send reminders

## Commands

### Getting Started
| Command | Description |
|---------|-------------|
| `?register <username>` | Link your Loomio account |
| `?status` | Check registration status |
| `?help` | Show all commands |

### Creating Polls
| Command | Description |
|---------|-------------|
| `?propose <title>` | Create a proposal |
| `?poll <title> \| opt1 \| opt2 \| ...` | Create a poll |
| `?score <title> \| opt1 \| opt2 \| ...` | Create a score poll (0-10) |
| `?rank <title> \| opt1 \| opt2 \| ...` | Create a ranked choice poll |
| `?meeting <title> \| time1 \| time2...` | Schedule a meeting |

### Voting
| Command | Description |
|---------|-------------|
| `?vote <id> <choice> [reason]` | Cast your vote |
| `?unvote <id>` | Remove your vote |
| `?my-votes` | Show your voting history |

### Results
| Command | Description |
|---------|-------------|
| `?results <id>` | Show poll results |
| `?polls` | List active polls |
| `?deadline <id>` | Show when poll closes |

### Discussion
| Command | Description |
|---------|-------------|
| `?comment <id> <text>` | Add a comment |
| `?discuss <id>` | Show recent comments |

### Admin
| Command | Description |
|---------|-------------|
| `?close <id>` | Close poll early |
| `?extend <id> <hours>` | Extend deadline |
| `?reopen <id>` | Reopen closed poll |
| `?remind <id>` | Send reminder |
| `?whohasnt <id>` | List non-voters |

## Configuration

| Variable | Description |
|----------|-------------|
| `LOOMIO_URL` | Your Loomio instance URL |
| `LOOMIO_API_KEY` | Loomio API key |

## Requirements

Requires a Loomio instance with the B1 API. See the [loomio-fork](https://github.com/thrillhousedev/loomio-fork) repository for the required API extensions.
