#!/bin/bash
# OMI Live Transcription Test Script - REAL STREAMING
# Connects to Bridge WebSocket and streams actual OMI transcripts
# Wake phrase: "hey openclaw" or "hey open claw"
# End phrases: "thanks" or "thank you"

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
BRIDGE_HOST="${BRIDGE_HOST:-localhost}"
BRIDGE_PORT="${BRIDGE_PORT:-8081}"
WS_URL="ws://${BRIDGE_HOST}:${BRIDGE_PORT}/ws"

# Ngrok public URL for the bridge (set on Omi device as webhook target)
# Omi device POSTs to: POST ${NGROK_URL}/transcript
NGROK_URL="${NGROK_URL:-https://unleased-unambiguously-jenice.ngrok-free.dev}"
TRANSCRIPT_ENDPOINT="${NGROK_URL}/transcript"

echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       OMI Live Transcription Test - REAL STREAMING       ║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  Wake phrase: ${GREEN}'hey openclaw'${CYAN} or ${GREEN}'hey open claw'${CYAN}           ║${NC}"
echo -e "${CYAN}║  End phrases: ${GREEN}'thanks'${CYAN} or ${GREEN}'thank you'${CYAN}                     ║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  Omi webhook endpoint (configure on device):             ║${NC}"
echo -e "${CYAN}║  ${GREEN}POST ${TRANSCRIPT_ENDPOINT}${CYAN}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Quick smoke test: send a test transcript via the ngrok endpoint
if [ "${1}" = "--test-send" ]; then
    echo -e "${YELLOW}→ Sending test transcript to ${TRANSCRIPT_ENDPOINT} ...${NC}"
    response=$(curl -s -X POST "${TRANSCRIPT_ENDPOINT}" \
        -H 'Content-Type: application/json' \
        -d '{"text": "Hey OpenClaw, test message"}')
    echo -e "${GREEN}Response:${NC} ${response}"
    exit 0
fi

# Check if websocat is installed
if ! command -v websocat &> /dev/null; then
    echo -e "${RED}✗${NC} websocat is not installed"
    echo -e "${YELLOW}  Install with: brew install websocat${NC}"
    exit 1
fi

# State variables
TRANSCRIPT_BUFFER=""
WAKE_DETECTED=false
BUILDING_COMMAND=""
COMMAND_READY=false
FINAL_COMMAND=""

echo -e "${BLUE}→${NC} Connecting to Bridge WebSocket at ${WS_URL}..."
echo ""

# Function to parse and display transcript
parse_transcript() {
    local text="$1"
    local ts="$2"

    # Add to rolling buffer (keep last 200 chars)
    TRANSCRIPT_BUFFER="${TRANSCRIPT_BUFFER} ${text}"
    TRANSCRIPT_BUFFER="${TRANSCRIPT_BUFFER: -200}"

    # Display the transcript line
    echo -e "${BLUE}[${ts}]${NC} ${CYAN}${text}${NC}"

    # Check for wake word (case insensitive, handles "hey openclaw" or "hey open claw")
    if echo "$TRANSCRIPT_BUFFER" | grep -qiE "hey\s+(open\s*claw|openclaw)"; then
        if [ "$WAKE_DETECTED" = false ]; then
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${GREEN}🎤 WAKE WORD DETECTED!${NC}"
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            WAKE_DETECTED=true
        fi

        # Extract everything after wake word
        local after_wake=$(echo "$text" | sed -E 's/.*hey\s+(open\s*claw|openclaw)\s*//i')

        # Check for end phrases
        if echo "$text" | grep -qiE "(thanks|thank you)"; then
            echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${CYAN}🛑 END PHRASE DETECTED - COMMAND COMPLETE${NC}"
            echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

            # Extract command between wake word and end phrase
            local command=$(echo "$BUILDING_COMMAND $after_wake" | sed -E 's/\s*(thanks|thank you).*//' | xargs)

            if [ -n "$command" ]; then
                echo ""
                echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
                echo -e "${YELLOW}║  📝 PARSED COMMAND FOR DISPATCH BAR                       ║${NC}"
                echo -e "${YELLOW}╠════════════════════════════════════════════════════════════╣${NC}"
                echo -e "${YELLOW}║${NC}  ${GREEN}${command}${NC}"
                echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
                echo ""

                FINAL_COMMAND="$command"
                COMMAND_READY=true

                # Reset state
                WAKE_DETECTED=false
                BUILDING_COMMAND=""
                TRANSCRIPT_BUFFER=""
            else
                echo -e "${RED}⚠${NC}  No command text found between wake word and end phrase"
                WAKE_DETECTED=false
                BUILDING_COMMAND=""
            fi
        else
            # Building command, accumulate
            if [ -n "$after_wake" ]; then
                BUILDING_COMMAND="${BUILDING_COMMAND} ${after_wake}"
                echo -e "${MAGENTA}📝 Building command: ${BUILDING_COMMAND}${NC}"
            fi
        fi
    fi
}

# Main streaming loop
echo -e "${YELLOW}Listening for OMI transcripts...${NC}"
echo -e "${YELLOW}Speak into your OMI device now!${NC}"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Connect to WebSocket and process messages
websocat "$WS_URL" | while IFS= read -r line; do
    # Parse JSON message
    if echo "$line" | grep -q '"type":"transcript"'; then
        # Extract text and timestamp using simple string manipulation
        text=$(echo "$line" | sed -E 's/.*"text":"([^"]+)".*/\1/')
        ts=$(echo "$line" | sed -E 's/.*"ts":"([^"]+)".*/\1/')

        # Handle if text or ts extraction failed
        if [ "$text" = "$line" ]; then
            text=$(echo "$line" | grep -oP '"text":"\K[^"]+' || echo "")
        fi
        if [ "$ts" = "$line" ]; then
            ts=$(date '+%H:%M:%S')
        fi

        if [ -n "$text" ]; then
            parse_transcript "$text" "$ts"
        fi
    fi
done

# This runs if WebSocket disconnects
echo ""
echo -e "${RED}WebSocket disconnected${NC}"

if [ "$COMMAND_READY" = true ] && [ -n "$FINAL_COMMAND" ]; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ Final parsed command:${NC} $FINAL_COMMAND"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
fi
