#!/bin/bash
# OMI Live Transcription Test Script
# Tests OMI wake word detection and command parsing in isolation
# Wake phrase: "hey openclaw"
# End phrases: "thanks" or "thank you"

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BRIDGE_PORT=8081
BRIDGE_URL="http://localhost:${BRIDGE_PORT}"
TRANSCRIPT_ENDPOINT="${BRIDGE_URL}/transcript"

echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       OMI Live Transcription Test - Isolated Mode        ║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  Wake phrase: ${GREEN}'hey openclaw'${CYAN}                              ║${NC}"
echo -e "${CYAN}║  End phrases: ${GREEN}'thanks'${CYAN} or ${GREEN}'thank you'${CYAN}                     ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if bridge is running
check_bridge() {
    echo -e "${BLUE}→${NC} Checking if Bridge is running on port ${BRIDGE_PORT}..."
    if curl -s -f "${BRIDGE_URL}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Bridge is running"
        return 0
    else
        echo -e "${RED}✗${NC} Bridge is not running"
        echo -e "${YELLOW}  Start the bridge with: cd bridge && uvicorn main:app --port ${BRIDGE_PORT}${NC}"
        return 1
    fi
}

# Parse transcription for wake word and command
parse_transcription() {
    local text="$1"
    local buffer="${TRANSCRIPT_BUFFER} ${text}"

    # Keep only last 200 chars in buffer
    buffer="${buffer: -200}"
    TRANSCRIPT_BUFFER="$buffer"

    # Check for wake word (case insensitive)
    if echo "$buffer" | grep -qiE "hey\s+(open\s*claw|openclaw)"; then
        echo -e "${GREEN}🎤 WAKE WORD DETECTED!${NC}"

        # Extract everything after wake word
        local after_wake=$(echo "$text" | sed -E 's/.*hey\s+(open\s*claw|openclaw)\s*//i')

        # Check for end phrases
        if echo "$text" | grep -qiE "(thanks|thank you)"; then
            echo -e "${CYAN}🛑 END PHRASE DETECTED${NC}"

            # Extract command between wake word and end phrase
            local command=$(echo "$after_wake" | sed -E 's/\s*(thanks|thank you).*//')

            if [ -n "$command" ]; then
                echo ""
                echo -e "${YELLOW}╔════════════════════════════════════════════════╗${NC}"
                echo -e "${YELLOW}║  📝 PARSED COMMAND FOR DISPATCH BAR           ║${NC}"
                echo -e "${YELLOW}╠════════════════════════════════════════════════╣${NC}"
                echo -e "${YELLOW}║${NC}  ${GREEN}${command}${NC}"
                echo -e "${YELLOW}╚════════════════════════════════════════════════╝${NC}"
                echo ""

                LAST_COMMAND="$command"
                COMMAND_READY=true
            else
                echo -e "${RED}⚠${NC}  No command text found between wake word and end phrase"
            fi
        else
            # Building command, show partial
            if [ -n "$after_wake" ]; then
                echo -e "${CYAN}📝 Building command:${NC} $after_wake"
                PARTIAL_COMMAND="$after_wake"
            fi
        fi
    fi
}

# Send test transcript via curl
send_transcript() {
    local text="$1"
    local response=$(curl -s -X POST "$TRANSCRIPT_ENDPOINT" \
        -H "Content-Type: application/json" \
        -d "{\"text\":\"$text\"}")

    if [ $? -eq 0 ]; then
        echo -e "${BLUE}→${NC} Sent: ${text}"
        parse_transcription "$text"
        return 0
    else
        echo -e "${RED}✗${NC} Failed to send transcript"
        return 1
    fi
}

# Main test flow
main() {
    # Initialize state
    TRANSCRIPT_BUFFER=""
    LAST_COMMAND=""
    PARTIAL_COMMAND=""
    COMMAND_READY=false

    # Check bridge availability
    if ! check_bridge; then
        exit 1
    fi

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Starting live transcription simulation...${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Test scenarios
    echo -e "${YELLOW}Test 1: Basic wake word + command + end phrase${NC}"
    echo "---"
    send_transcript "hey openclaw what is the weather today thanks"
    sleep 1
    echo ""

    echo -e "${YELLOW}Test 2: Multiple words spoken separately${NC}"
    echo "---"
    TRANSCRIPT_BUFFER=""
    send_transcript "um"
    sleep 0.5
    send_transcript "hey openclaw"
    sleep 0.5
    send_transcript "check the status"
    sleep 0.5
    send_transcript "of all nodes thank you"
    sleep 1
    echo ""

    echo -e "${YELLOW}Test 3: Wake word with longer command${NC}"
    echo "---"
    TRANSCRIPT_BUFFER=""
    send_transcript "hey openclaw deploy the new version to production and run all tests thanks"
    sleep 1
    echo ""

    echo -e "${YELLOW}Test 4: No wake word (should be ignored)${NC}"
    echo "---"
    TRANSCRIPT_BUFFER=""
    send_transcript "just some random speech without the wake word"
    sleep 1
    echo ""

    echo -e "${YELLOW}Test 5: Wake word but no end phrase yet${NC}"
    echo "---"
    TRANSCRIPT_BUFFER=""
    send_transcript "hey openclaw start analyzing the logs"
    sleep 1
    send_transcript "and send me a report"
    sleep 1
    send_transcript "when it's done thanks"
    sleep 1
    echo ""

    echo -e "${YELLOW}Test 6: Alternative wake word spelling${NC}"
    echo "---"
    TRANSCRIPT_BUFFER=""
    send_transcript "hey open claw restart the service thank you"
    sleep 1
    echo ""

    # Summary
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓${NC} Test completed!"
    echo ""

    if [ "$COMMAND_READY" = true ] && [ -n "$LAST_COMMAND" ]; then
        echo -e "${GREEN}Last parsed command:${NC} $LAST_COMMAND"
        echo -e "${CYAN}This would be entered into the dispatch bar.${NC}"
    fi

    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo -e "  1. Test with actual OMI device webhook"
    echo -e "  2. Integrate with swarm topology dispatch bar"
    echo -e "  3. Add OMI toggle button to UI"
    echo ""
}

# Run main test
main
