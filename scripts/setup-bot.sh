#!/usr/bin/env bash
#
# Interactive setup script for Signalinator bots
# Usage: ./scripts/setup-bot.sh [botname]
#
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Available bots with descriptions
declare -A BOT_DESCRIPTIONS=(
    ["conductinator"]="Docker container management via Signal"
    ["decisionator"]="Loomio integration for polls/decisions"
    ["informationator"]="RAG document Q&A (Ollama + ChromaDB)"
    ["informinator"]="Anonymous message relay"
    ["newsinator"]="RSS/Reddit/Bluesky feed aggregation"
    ["summarizinator"]="AI-powered chat summaries"
    ["taginator"]="@mention all group members"
)

BOTS=("conductinator" "decisionator" "informationator" "informinator" "newsinator" "summarizinator" "taginator")

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[Step $1]${NC} $2"
}

print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

print_error() {
    echo -e "${RED}Error:${NC} $1"
}

confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

select_bot() {
    print_header "Signalinator Bot Setup"
    echo "Select a bot to set up:"
    echo ""

    local i=1
    for bot in "${BOTS[@]}"; do
        printf "  ${CYAN}%d)${NC} %-18s %s\n" "$i" "$bot" "${BOT_DESCRIPTIONS[$bot]}"
        ((i++))
    done

    echo ""
    read -p "Enter choice [1-${#BOTS[@]}]: " choice

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#BOTS[@]}" ]; then
        BOT_NAME="${BOTS[$((choice-1))]}"
    else
        print_error "Invalid choice"
        exit 1
    fi
}

# Check if bot name provided as argument
if [ -z "$1" ]; then
    select_bot
else
    BOT_NAME="$1"

    # Validate bot name
    if [[ ! " ${BOTS[*]} " =~ " ${BOT_NAME} " ]]; then
        print_error "Unknown bot: $BOT_NAME"
        echo ""
        select_bot
    fi
fi

# Title case for display
BOT_DISPLAY=$(echo "$BOT_NAME" | sed 's/./\U&/')

print_header "Setup: $BOT_DISPLAY"

echo "This script will guide you through:"
echo "  1. Building the Docker image"
echo "  2. Registering the Signal account"
echo "  3. Setting the profile name and about text"
echo "  4. Setting the Signal username"
echo "  5. Starting the bot"
echo ""

if ! confirm "Ready to begin?"; then
    echo "Setup cancelled."
    exit 0
fi

# Step 1: Build
print_header "Step 1: Build"
print_step 1 "Building $BOT_NAME Docker image..."

docker compose --profile "$BOT_NAME" build

echo -e "${GREEN}Build complete!${NC}"

# Step 2: Registration
print_header "Step 2: Registration"

echo "Choose registration method:"
echo "  1) Register as PRIMARY device (new phone number)"
echo "  2) Link as SECONDARY device (existing Signal account)"
echo "  3) Skip (already registered)"
echo ""
read -p "Choice [1/2/3]: " REG_CHOICE

case "$REG_CHOICE" in
    1)
        print_step 2 "Registering as primary device..."
        echo ""
        echo "You will need:"
        echo "  - A CAPTCHA token from https://signalcaptchas.org/registration/generate.html"
        echo "  - Access to receive SMS/voice call at the bot's phone number"
        echo ""
        docker compose run --rm "${BOT_NAME}-daemon" setup
        ;;
    2)
        print_step 2 "Linking as secondary device..."
        echo ""
        docker compose run --rm "${BOT_NAME}-daemon" link --name "$BOT_NAME"
        echo ""
        echo "After scanning the QR code, press Enter to continue..."
        read -r
        ;;
    3)
        print_step 2 "Skipping registration (already registered)"
        ;;
    *)
        print_error "Invalid choice"
        exit 1
        ;;
esac

# Step 3: Profile
print_header "Step 3: Profile"

read -p "Display name for the bot [$BOT_DISPLAY]: " DISPLAY_NAME
DISPLAY_NAME="${DISPLAY_NAME:-$BOT_DISPLAY}"

read -p "About text (optional): " ABOUT_TEXT

print_step 3 "Setting profile..."

if [ -n "$ABOUT_TEXT" ]; then
    docker compose run --rm "${BOT_NAME}-daemon" profile --name "$DISPLAY_NAME" --about "$ABOUT_TEXT"
else
    docker compose run --rm "${BOT_NAME}-daemon" profile --name "$DISPLAY_NAME"
fi

echo -e "${GREEN}Profile set!${NC}"

# Step 4: Username
print_header "Step 4: Username"

echo "Signal usernames allow others to find and message the bot."
echo "Signal will add a discriminator (e.g., .25) to make it unique."
echo ""

read -p "Username for the bot [$BOT_DISPLAY]: " USERNAME
USERNAME="${USERNAME:-$BOT_DISPLAY}"

print_step 4 "Setting username..."

docker compose run --rm "${BOT_NAME}-daemon" username "$USERNAME"

echo -e "${GREEN}Username set!${NC}"

# Step 5: Start
print_header "Step 5: Start"

if confirm "Start $BOT_NAME now?"; then
    print_step 5 "Starting $BOT_NAME..."
    docker compose --profile "$BOT_NAME" up -d
    echo ""
    echo -e "${GREEN}$BOT_DISPLAY is now running!${NC}"
    echo ""
    echo "View logs with:"
    echo "  docker compose logs -f $BOT_NAME"
else
    echo ""
    echo "To start later, run:"
    echo "  docker compose --profile $BOT_NAME up -d"
fi

print_header "Setup Complete!"

echo "Your bot is configured with:"
echo "  Name: $DISPLAY_NAME"
echo "  Username: $USERNAME"
if [ -n "$ABOUT_TEXT" ]; then
    echo "  About: $ABOUT_TEXT"
fi
echo ""
echo "Useful commands:"
echo "  docker compose --profile $BOT_NAME up -d     # Start"
echo "  docker compose --profile $BOT_NAME stop      # Stop"
echo "  docker compose logs -f $BOT_NAME             # View logs"
echo "  docker compose run --rm ${BOT_NAME}-daemon status  # Check status"
echo ""
