# Migrating from Informinator to Helpinator

In v1.7, Informinator was rebranded to Helpinator and gained help-desk ticketing
on top of the existing relay engine. This guide walks an existing deployment
through the rebrand. It applies whether you run a single Informinator or two
(`informinator` and `informinator2`).

## What carries over and what resets

| Item | Action |
|------|--------|
| Signal phone registration (`config/<bot>/`) | **Renamed, not deleted.** No `link` / `setup` / SMS / CAPTCHA needed. |
| Phone number itself | Same number; lives under `HELPINATOR_PHONE` going forward. |
| Bot's Signal display name | Optional re-set after migration via admin DM `/set-name Helpinator`. |
| Database (`data/<bot>/`) | **Wiped.** Helpinator creates fresh `helpinator_*` tables on first start. Existing room pairs, sessions, and relay mappings are gone. |
| Existing room-pair setup | Re-run `/setup control` (and `/setup lobby` if you use lobbies) after start. |

If you have data you want to preserve, stop here and copy `data/informinator/`
elsewhere first — the procedure below removes it.

## Migration playbook

Run from the repo root on the deployment box.

### 1. Stop the running Informinators

```bash
docker compose --profile informinator down
docker compose --profile informinator2 down   # only if you run a second one
```

`down` (no `-v`) stops the containers and keeps the named volumes intact.

### 2. Pull the rebrand

```bash
git pull origin main
```

Confirm you're on the v1.7 line:

```bash
git log --oneline -1
```

### 3. Preserve signal-cli registration

```bash
mv config/informinator  config/helpinator
mv config/informinator2 config/helpinator2   # only if applicable
```

The `config/` directories hold private keys for the registered Signal account.
Renaming preserves them and avoids re-running the linking ceremony.

### 4. Wipe old bot data

```bash
rm -rf data/informinator data/informinator2
```

Helpinator creates `data/helpinator/` and `data/helpinator2/` on first start
with the new schema (`helpinator_*` tables including
`helpinator_control_room_config` and `helpinator_ticket_notes`).

### 5. Rename environment variables

The compose file expects `HELPINATOR_*` variables. Update `.env` in place:

```bash
cp .env .env.bak                              # safety net
sed -i 's/INFORMINATOR_/HELPINATOR_/g; s/INFORMINATOR2_/HELPINATOR2_/g' .env
grep -E "^HELPINATOR" .env                    # sanity check
```

On macOS / BSD `sed`, use `sed -i ''` (empty backup extension):

```bash
sed -i '' 's/INFORMINATOR_/HELPINATOR_/g; s/INFORMINATOR2_/HELPINATOR2_/g' .env
```

Variables you should now see, with their old values preserved:

- `HELPINATOR_PHONE`, `HELPINATOR_DAEMON_PORT`, optional `HELPINATOR_ADMINS`
- `HELPINATOR2_PHONE`, `HELPINATOR2_DAEMON_PORT`, optional `HELPINATOR2_ADMINS`

### 6. Build and start

```bash
docker compose --profile helpinator  build
docker compose --profile helpinator2 build   # only if applicable
docker compose --profile helpinator  up -d
docker compose --profile helpinator2 up -d
```

Daemons mount the renamed `config/helpinator/` and authenticate immediately
with the carried-over signal-cli keys — no `link` or `setup` step.

### 7. Verify

Tail the logs for each bot and confirm clean startup:

```bash
docker compose logs --tail=40 helpinator
docker compose logs --tail=40 helpinator2
```

You're looking for the bot connecting to Signal and resolving its own UUID.
No errors, no "registration not found" messages.

### 8. Re-set up the control room

Because the database was wiped, the bot has no record of its previous control
room. From the Signal group you want to use as the control room:

```
/setup control
```

If you use lobbies, run `/setup lobby` in each lobby group. Then:

```
/helpdesk
```

This shows the current state. Helpdesk mode defaults to `on` for new control
rooms; turn it `off` if you want plain message relay behavior identical to
Informinator's.

### 9. Optionally update the Signal display name

```
/set-name Helpinator
```

(Run as a DM to the bot from a UUID listed in `BOT_PROFILE_ADMINS`.)

You can also set this from the host with the daemon command:

```bash
docker compose run --rm helpinator-daemon profile --name "Helpinator" \
  --about "Help desk for Signal"
```

## Rollback

The migration is reversible up until step 6 (build/start). To roll back before
that point:

```bash
mv config/helpinator  config/informinator
mv config/helpinator2 config/informinator2
mv .env.bak .env
git checkout v1.6        # or whichever revision you came from
```

Once Helpinator has run and created its new `data/helpinator/` directory and
schema, rolling back means losing any tickets opened in the meantime. The
signal-cli registration in `config/` can still be moved back without losing
the Signal account.

## Smoke test

Once everything is up, confirm the help-desk path end-to-end:

1. From a separate Signal account, DM the bot. You should receive a greeting
   that includes a ticket number (e.g. `🎫 Ticket #1 opened.`).
2. In the control room you should see `🎫 Ticket #1 opened by <Display>: ...`.
3. From the control room, run `/tickets` — ticket #1 appears.
4. Quote-reply the forwarded message in the control room — the user receives
   the reply via DM.
5. Run `/close #1 verified working` — the user receives
   `✅ Ticket #1 resolved: verified working` and the control room sees
   `✅ Ticket #1 closed by <agent>`.

If any step fails, `docker compose logs -f helpinator` will surface the cause.
