# Helpinator

Signal help desk bot. End-users DM the bot to open a ticket; agents in a Control Room triage, reply, add internal notes, and close with a resolution that gets DM'd back to the user.

Helpdesk mode is on by default. It can be turned off per control room (`/helpdesk off`) to fall back to plain message relay.

## How It Works

```
  User DM ──→ Helpinator ──→ Control Room
              (opens ticket #N)
                              agents quote-reply → user DM
                              /note, /subject, /close, /export
```

**Example flow:**
1. User DMs the bot: `email isn't sending`
2. Bot opens ticket #1, replies to user with greeting
3. Control room sees: `🎫 Ticket #1 opened by Alice: email isn't sending`
4. Agent quote-replies: `Try restarting Outlook` → DM'd to Alice
5. Agent runs `/note #1 user already tried restart; escalating`
6. Agent runs `/close #1 Reinstalled Outlook — resolved` → Alice receives `✅ Ticket #1 resolved: ...`

Optional lobbies can be used as an onboarding vehicle: users join a public lobby group, get greeted, then DM the bot.

## Commands

### Help desk (Control Room, Admin)

Require `@Helpinator` mention.

| Command | Description |
|---------|-------------|
| `/helpdesk [on\|off]` | Toggle or show helpdesk mode |
| `/tickets [open\|closed\|all] [page]` | List tickets, newest first |
| `/ticket <#n>` | Full ticket details including notes |
| `/close <#n> <resolution>` | Close ticket and DM the resolution to the user |
| `/subject <#n> <text>` | Update a ticket's subject |
| `/note <#n> <text>` | Append an immutable internal note (not sent to user) |
| `/export tickets [open\|closed\|all] [csv\|md]` | Export as an attachment in the control room |

Agent replies to user messages are done via Signal's quote-reply — no command needed.

### Setup (Admin)

| Command | Description |
|---------|-------------|
| `/setup control` | Mark this group as the control room |
| `/setup lobby` | Mark this group as a lobby |
| `/unpair` | Remove room pairing |
| `/status` | Show room role and pairing info |
| `/sessions` | List active conversations |

### Privacy (Admin)

| Command | Description |
|---------|-------------|
| `/anonymous on\|off` | Pseudonym mode for lobby users |
| `/dm-anonymous on\|off` | Pseudonym mode for direct DM users |
| `/confirmations on\|off` | ✅ delivery reactions |
| `/retention <days>` | Session auto-purge (0 disables) |
| `/greeting [msg]` | Lobby welcome message |
| `/authorize <uuid> \| list \| revoke <uuid>` | Control which users can link lobbies |

### User DM commands

Available to users messaging the bot directly.

| Command | Description |
|---------|-------------|
| `/dm-anonymous off` | Reveal your identity (ends anonymous session, starts new revealed session) |
| `/dm-anonymous on` | Re-anonymize (next message gets a new pseudonym) |
| `/dm-anonymous` | Check your current anonymous status |
| `/end-session` | Close your ticket / end your session |

`/dm-anonymous` rotations start a new session, which in helpdesk mode also starts a new ticket.

## Ticket lifecycle

- **Open** — ticket created when a new direct-DM session begins in helpdesk mode. Subject auto-set from the first message (editable via `/subject`).
- **Resolved** — agent ran `/close <#n> <resolution>`. Resolution is DM'd to the user; session is ended.
- **Closed by user** — user ran `/end-session`. No resolution; control room is notified.

Closed tickets remain queryable (`/ticket #n`, `/tickets closed`, `/export tickets closed`). Notes can still be appended to closed tickets for post-mortems.

## Privacy

**No message content is stored** — only routing metadata:
- Room pair configurations (lobby/control mapping)
- Sessions (ticket user, status, ticket fields)
- Relay mappings (auto-purged after 72 hours)
- Internal notes and resolutions (intentionally persisted with tickets)

**Not stored:** forwarded message bodies, attachments, user profiles.

## Security

- SQLCipher (AES-256) database encryption
- Pseudonym mode hides user identities from agents
- Internal notes are immutable at the repository layer — never updated or deleted
