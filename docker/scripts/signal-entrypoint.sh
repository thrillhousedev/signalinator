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
            exec signal-cli -a "$PHONE" --config "$CONFIG_DIR" \
                --trust-new-identities=always \
                daemon --http 0.0.0.0:8080 --receive-mode=on-connection
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
            exec signal-cli -a "$PHONE" --config "$CONFIG_DIR" \
                --trust-new-identities=always \
                daemon --http 0.0.0.0:8080 --receive-mode=on-connection
        fi
        ;;
    *)
        # Pass through any other commands
        exec "$@"
        ;;
esac
