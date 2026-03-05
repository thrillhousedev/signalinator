# Informinator

Anonymous message relay for Signal - connects public-facing lobby rooms to a private operator control room.

Informinator sits between paired Signal groups: **lobbies** (public-facing) and a **control room** (operators). People join any lobby, get greeted, and DM the bot. The bot relays DMs to the control room with the sender's identity (or a pseudonym in anonymous mode). Operators reply to relayed messages and the bot sends the reply back to the original sender.

## Features

- **Room Pairing**: Link lobby and control groups with `/setup lobby` and `/setup control`
- **Multiple Lobbies**: Connect multiple lobbies to a single control room
- **Message Relay**: User DMs forwarded to control room, operator replies go back to users
- **Anonymous Mode**: Optional pseudonyms ("User A", "User B") hide real identities
- **Attachment Forwarding**: Images, files, voice messages relayed in both directions
- **Reply Detection**: Operators reply by quoting forwarded messages

## How It Works

```
  Lobby A ─────┐
               │              Informinator Bot               Control Room
  Lobby B ─────┼─────────────→ Forwards DMs to      ────→  All messages from
               │               control room                 all lobbies
  Lobby C ─────┘              ←───────────────────────────  Operators reply
                              Relays back to sender
```

**Example flow:**
1. User joins Lobby A → Bot greets them, notifies control: "[Lobby A] Alice joined"
2. User DMs bot → Bot forwards to control: "[Lobby A] Alice: I need help"
3. Operator quotes and replies → Bot DMs the reply back to Alice

## Commands

All commands require `@Informinator` mention in groups, or can be sent as DMs.

| Command | Description | Permission |
|---------|-------------|-----------|
| `/setup lobby` | Mark this group as a lobby | Admin |
| `/setup control` | Mark this group as a control room (pairs with pending lobby) | Admin |
| `/unpair` | Remove room pairing | Admin |
| `/status` | Show room role and pairing info | Anyone |
| `/anonymous on\|off` | Toggle pseudonym mode | Admin |
| `/greeting [msg]` | Set/view the lobby greeting message | Admin |
| `/dm` | Bot DMs the sender (for lobby users) | Anyone |
| `/rejoin` | Bot re-invites admin to lobby (from control room) | Admin |
| `/help` | Show available commands | Anyone |

## Privacy

**No messages are stored** - only routing metadata:
- Room pair configurations (lobby/control mapping)
- Active sessions (which users are in which lobbies)
- Relay mappings (auto-deleted after 72 hours)

**Never stored:** Message content, attachments, phone numbers, user profiles.

## Security

- Database encryption with SQLCipher (AES-256)
- Messages pass through without persistence
- Anonymous mode hides user identities from operators
