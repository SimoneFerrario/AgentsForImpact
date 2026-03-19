#!/usr/bin/env bash
# test-vnc.sh — Check and restart ttyd/cloudflared tunnels on nemoclaw-1 and nemoclaw-2

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────
log_info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_err()   { echo -e "${RED}[ERR]${RESET}   $*"; }

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
  local raw
  raw=$(brev exec "$name" "grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cf-ttyd.log | tail -1" 2>&1)
  # Extract just the URL in case brev appends instance name or extra text
  echo "$raw" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | head -1
}

start_cloudflared() {
  local name="$1"
  log_warn "$name: cloudflared tunnel down — restarting..."
  brev exec "$name" "pkill cloudflared 2>/dev/null; nohup /tmp/cloudflared tunnel --url http://localhost:7681 --no-autoupdate > /tmp/cf-ttyd.log 2>&1 &" 2>&1
  log_info "$name: waiting 8s for tunnel to establish..."
  sleep 8
}

# ── Per-instance logic ────────────────────────────────────────────────────────
# Returns the URL via stdout; caller captures it.
handle_instance() {
  local name="$1"
  local url=""

  echo "" >&2
  echo -e "${BOLD}━━━ $name ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}" >&2

  # 1. Check ttyd
  if check_ttyd "$name"; then
    log_ok "$name: ttyd is alive" >&2
  else
    start_ttyd "$name"
    if check_ttyd "$name"; then
      log_ok "$name: ttyd restarted successfully" >&2
    else
      log_err "$name: ttyd failed to start — aborting tunnel check" >&2
      echo "UNAVAILABLE"
      return
    fi
  fi

  # 2. Try to fetch existing cloudflared URL
  url=$(get_cf_url "$name")

  if [[ -n "$url" && "$url" =~ ^https:// ]]; then
    log_ok "$name: existing tunnel URL found: $url" >&2
    echo "$url"
    return
  fi

  # 3. Restart cloudflared and get new URL
  start_cloudflared "$name"
  url=$(get_cf_url "$name")

  if [[ -n "$url" && "$url" =~ ^https:// ]]; then
    log_ok "$name: new tunnel URL: $url" >&2
    echo "$url"
  else
    log_err "$name: could not obtain cloudflared URL" >&2
    echo "UNAVAILABLE"
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║         ttyd / cloudflared Health Check          ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

URL1=$(handle_instance "nemoclaw-1")
URL2=$(handle_instance "nemoclaw-2")

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
for pair in "nemoclaw-1:$URL1" "nemoclaw-2:$URL2"; do
  inst="${pair%%:*}"
  url="${pair#*:}"
  if [[ "$url" == "UNAVAILABLE" || -z "$url" ]]; then
    echo -e "${RED}✗ $inst: UNAVAILABLE${RESET}"
  else
    echo -e "${GREEN}✓ $inst: $url${RESET}"
  fi
done
echo ""

# ── Open in browser ───────────────────────────────────────────────────────────
log_info "Opening URLs in browser..."
opened=0
for url in "$URL1" "$URL2"; do
  if [[ -n "$url" && "$url" != "UNAVAILABLE" ]]; then
    open "$url" 2>/dev/null || true
    opened=$((opened + 1))
  fi
done
[[ $opened -eq 0 ]] && log_warn "No valid URLs to open."
