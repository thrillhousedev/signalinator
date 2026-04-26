#!/bin/bash
# Create a new bot from the template
#
# Usage: ./scripts/create-bot.sh mybot "My awesome bot description"

set -e

BOT_NAME="$1"
BOT_DESCRIPTION="${2:-A Signal bot}"

if [ -z "$BOT_NAME" ]; then
    echo "Usage: $0 <bot_name> [description]"
    echo "Example: $0 mybot \"My awesome Signal bot\""
    exit 1
fi

# Validate bot name (lowercase, no spaces)
if [[ ! "$BOT_NAME" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "Error: Bot name must be lowercase, start with a letter, and contain only letters, numbers, and underscores"
    exit 1
fi

# Generate class name (PascalCase + Bot) - compatible with macOS and Linux
# Pass BOT_NAME via environment to avoid shell injection in Python string
BOT_CLASS=$(BOT_NAME="$BOT_NAME" python3 -c "import os; print(''.join(w.capitalize() for w in os.environ['BOT_NAME'].split('_')) + 'Bot')")
BOT_TITLE=$(BOT_NAME="$BOT_NAME" python3 -c "import os; print(''.join(w.capitalize() for w in os.environ['BOT_NAME'].split('_')))")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$REPO_ROOT/templates/new-bot"
BOT_DIR="$REPO_ROOT/bots/$BOT_NAME"

if [ -d "$BOT_DIR" ]; then
    echo "Error: Bot directory already exists: $BOT_DIR"
    exit 1
fi

echo "Creating bot: $BOT_NAME"
echo "  Class: $BOT_CLASS"
echo "  Title: $BOT_TITLE"
echo "  Description: $BOT_DESCRIPTION"
echo ""

# Create directory structure
mkdir -p "$BOT_DIR/src/$BOT_NAME/database"
mkdir -p "$BOT_DIR/src/$BOT_NAME/cli"

# Process templates (use | as sed delimiter to avoid conflicts with description text)
process_template() {
    local src="$1"
    local dst="$2"

    sed -e "s|{{BOT_NAME}}|$BOT_NAME|g" \
        -e "s|{{BOT_CLASS}}|$BOT_CLASS|g" \
        -e "s|{{BOT_TITLE}}|$BOT_TITLE|g" \
        -e "s|{{BOT_DESCRIPTION}}|$BOT_DESCRIPTION|g" \
        "$src" > "$dst"

    echo "  Created: $dst"
}

process_template "$TEMPLATE_DIR/pyproject.toml.template" "$BOT_DIR/pyproject.toml"
process_template "$TEMPLATE_DIR/src/__init__.py.template" "$BOT_DIR/src/$BOT_NAME/__init__.py"
process_template "$TEMPLATE_DIR/src/bot.py.template" "$BOT_DIR/src/$BOT_NAME/bot.py"
process_template "$TEMPLATE_DIR/src/database/__init__.py.template" "$BOT_DIR/src/$BOT_NAME/database/__init__.py"
process_template "$TEMPLATE_DIR/src/database/models.py.template" "$BOT_DIR/src/$BOT_NAME/database/models.py"
process_template "$TEMPLATE_DIR/src/database/repository.py.template" "$BOT_DIR/src/$BOT_NAME/database/repository.py"
process_template "$TEMPLATE_DIR/src/cli/__init__.py.template" "$BOT_DIR/src/$BOT_NAME/cli/__init__.py"

# Create config and data directories
mkdir -p "$REPO_ROOT/config/$BOT_NAME"
mkdir -p "$REPO_ROOT/data/$BOT_NAME"

echo ""
echo "Bot created successfully!"
echo ""
echo "Next steps:"
BOT_NAME_UPPER=$(BOT_NAME="$BOT_NAME" python3 -c "import os; print(os.environ['BOT_NAME'].upper())")
echo "  1. Add to .env:"
echo "     ${BOT_NAME_UPPER}_PHONE=+1XXXXXXXXXX"
echo "     ${BOT_NAME_UPPER}_DAEMON_PORT=808X"
echo ""
echo "  2. Add to docker-compose.yml (copy from existing bot)"
echo ""
echo "  3. Install the package:"
echo "     pip install -e bots/$BOT_NAME"
echo ""
echo "  4. Customize your bot in:"
echo "     bots/$BOT_NAME/src/$BOT_NAME/bot.py"
