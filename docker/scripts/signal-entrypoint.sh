#!/bin/bash
set -e

CONFIG_DIR="/signal-cli-config"
PHONE="$SIGNAL_PHONE_NUMBER"

# Check if account is registered by verifying accounts.json has entries
is_registered() {
    local accounts_file="$CONFIG_DIR/data/accounts.json"
    [ -f "$accounts_file" ] || return 1
    # Use jq-like check with Python - exit 0 if accounts array is non-empty
    python3 -c 'import json,sys; d=json.load(open("/signal-cli-config/data/accounts.json")); sys.exit(0 if d.get("accounts") else 1)' 2>/dev/null
}

# Start signal-cli daemon with retry logic for transient connection failures.
# Retries within the container are much faster than full container restarts.
start_daemon() {
    local max_retries=5
    local base_delay=5
    local attempt=0

    while [ $attempt -lt $max_retries ]; do
        attempt=$((attempt + 1))

        # Final attempt: exec so signal-cli becomes PID 1 for proper signal handling
        if [ $attempt -eq $max_retries ]; then
            echo "Starting signal-cli daemon (attempt $attempt/$max_retries, final)..."
            exec signal-cli -a "$PHONE" --config "$CONFIG_DIR" \
                --trust-new-identities=always \
                daemon --http 0.0.0.0:8080 --receive-mode=on-connection
        fi

        echo "Starting signal-cli daemon (attempt $attempt/$max_retries)..."
        signal-cli -a "$PHONE" --config "$CONFIG_DIR" \
            --trust-new-identities=always \
            daemon --http 0.0.0.0:8080 --receive-mode=on-connection && exit 0 || true

        # Exponential backoff: 5s, 10s, 20s, 40s (capped at 60s) + random jitter 0-5s
        local delay=$(( base_delay * (1 << (attempt - 1)) ))
        [ $delay -gt 60 ] && delay=60
        local jitter=$(( RANDOM % 6 ))
        delay=$(( delay + jitter ))

        echo "signal-cli exited unexpectedly. Retrying in ${delay}s..."
        sleep "$delay"
    done
}

# Handle different commands
case "${1:-}" in
    setup|link|status|profile|username)
        # Run the setup CLI command
        exec python3 /app/signal-setup.py "$@"
        ;;
    ""|daemon)
        # Default: run daemon or wait for registration
        if is_registered; then
            echo "Account registered. Starting signal-cli daemon..."
            # --trust-new-identities=always: auto-trust when users reinstall Signal
            start_daemon
        else
            echo "=================================================="
            echo "  Account not registered!"
            echo "  "
            echo "  Run setup with:"
            echo "    docker compose run --rm <bot>-daemon setup"
            echo "  "
            echo "  Or link as secondary device:"
            echo "    docker compose run --rm <bot>-daemon link"
            echo "=================================================="
            echo ""
            echo "Waiting for registration... (checking every 10s)"

            # Keep container alive, checking every 10s
            while ! is_registered; do
                sleep 10
            done

            echo "Registration detected! Starting daemon..."
            # --trust-new-identities=always: auto-trust when users reinstall Signal
            start_daemon
        fi
        ;;
    *)
        # Pass through any other commands
        exec "$@"
        ;;
esac
