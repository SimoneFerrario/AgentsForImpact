#!/bin/bash
export NVM_DIR=$HOME/.nvm
source $NVM_DIR/nvm.sh 2>/dev/null
export PATH=$HOME/.nvm/versions/node/v22.22.1/bin:$PATH

clear
echo '╔════════════════════════════════════════════╗'
echo '║   🦞 NEMOCLAW AGENT — OPENCLAW GATEWAY    ║'
echo '╚════════════════════════════════════════════╝'
echo ''

# Show hostname
echo "  Instance: $(hostname)"
echo "  Time:     $(date '+%H:%M:%S')"
echo ''

# Service status
echo '  Services:'
pgrep -f server.py > /dev/null && echo '    ✓ AgentsForImpact server (port 8080)' || echo '    ✗ server.py NOT running'
pgrep -f ttyd > /dev/null && echo '    ✓ ttyd terminal (port 7681)' || echo '    ✗ ttyd not running'
echo ''

echo '════════════════════════════════════════════'
echo '  📡 LIVE TASK LOG — Waiting for dispatch...'
echo '════════════════════════════════════════════'
echo ''

# Tail server log — shows incoming requests and pipeline activity
tail -f /tmp/server.log 2>/dev/null &
TAIL_PID=$!

# Also watch for v0 deploy activity
tail -f /tmp/v0-deploy.log 2>/dev/null &

wait $TAIL_PID
