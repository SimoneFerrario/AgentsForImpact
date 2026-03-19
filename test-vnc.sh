#!/usr/bin/env bash
# test-vnc.sh — Check and restart ttyd/cloudflared tunnels on nemoclaw-1 and nemoclaw-2

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

INSTANCES=("nemoclaw-1" "nemoclaw-2")
declare -A URLS

# ── Helpers ───────────────────────────────────────────────────────────────────
log_info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_err()     { echo -e "${RED}[ERR]${RESET}   $*"; }

check_ttyd() {
  local name="$1"
  local result
  result=$(brev exec "$name" "curl -s http://localhost:7681 | head -c 50 || echo 'ttyd down'" 2>&1)
  if echo "$result" | grep -qi "ttyd down"; then
    return 1
  fi
  return 0
}

start_ttyd() {
  local name="$1"
  log_warn "$name: ttyd is down — restarting..."
  brev exec "$name" "pkill ttyd 2>/dev/null; /tmp/ttyd -p 7681 bash > /tmp/ttyd.log 2>&1 &" 2>&1
  sleep 2
}

get_cf_url() {
  local name="$1"
  brev exec "$name" "grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cf-ttyd.log | tail -1" 2>&1 | tr -d '[:space:]'
}

start_cloudflared() {
  local name="$1"
  log_warn "$name: cloudflared tunnel down — restarting..."
  brev exec "$name" "pkill cloudflared 2>/dev/null; nohup /tmp/cloudflared tunnel --url http://localhost:7681 --no-autoupdate > /tmp/cf-ttyd.log 2>&1 &" 2>&1
  log_info "$name: waiting 8s for tunnel to establish..."
  sleep 8
}

# ── Per-instance logic ────────────────────────────────────────────────────────
handle_instance() {
  local name="$1"
  echo ""
  echo -e "${BOLD}━━━ $name ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

  # 1. Check ttyd
  if check_ttyd "$name"; then
    log_ok "$name: ttyd is alive"
  else
    start_ttyd "$name"
    # Verify restart
    if check_ttyd "$name"; then
      log_ok "$name: ttyd restarted successfully"
    else
      log_err "$name: ttyd failed to start — aborting tunnel check"
      URLS["$name"]="UNAVAILABLE"
      return
    fi
  fi

  # 2. Try to fetch existing cloudflared URL
  local url
  url=$(get_cf_url "$name")

  if [[ -n "$url" && "$url" =~ ^https:// ]]; then
    log_ok "$name: existing tunnel URL found: $url"
    URLS["$name"]="$url"
  else
    # 3. Restart cloudflared
    start_cloudflared "$name"
    url=$(get_cf_url "$name")

    if [[ -n "$url" && "$url" =~ ^https:// ]]; then
      log_ok "$name: new tunnel URL: $url"
      URLS["$name"]="$url"
    else
      log_err "$name: could not obtain cloudflared URL"
      URLS["$name"]="UNAVAILABLE"
    fi
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║         ttyd / cloudflared Health Check          ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

for instance in "${INSTANCES[@]}"; do
  handle_instance "$instance"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
for instance in "${INSTANCES[@]}"; do
  url="${URLS[$instance]:-UNAVAILABLE}"
  if [[ "$url" == "UNAVAILABLE" ]]; then
    echo -e "${RED}✗ $instance: UNAVAILABLE${RESET}"
  else
    echo -e "${GREEN}✓ $instance: $url${RESET}"
  fi
done
echo ""

# ── Open in browser ───────────────────────────────────────────────────────────
URL1="${URLS[nemoclaw-1]:-}"
URL2="${URLS[nemoclaw-2]:-}"

OPEN_ARGS=()
[[ -n "$URL1" && "$URL1" != "UNAVAILABLE" ]] && OPEN_ARGS+=("$URL1")
[[ -n "$URL2" && "$URL2" != "UNAVAILABLE" ]] && OPEN_ARGS+=("$URL2")

if [[ ${#OPEN_ARGS[@]} -gt 0 ]]; then
  log_info "Opening URLs in browser..."
  for url in "${OPEN_ARGS[@]}"; do
    open "$url"
  done
else
  log_warn "No valid URLs to open."
fi
