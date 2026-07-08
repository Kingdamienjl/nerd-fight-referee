#!/usr/bin/env bash 
set -u 

REPO="/mnt/d/Projects/trae_projects/AI nerd fight decision bot discord" 
HOME_DIR="/home/kingdamienjl/ai_nerd_referee_proactive" 
LIVE_LOG="$HOME_DIR/live.log" 
STATUS="$HOME_DIR/status.txt" 

mkdir -p "$HOME_DIR" 

cd "$REPO" || exit 1 
source .venv/bin/activate 

echo "Proactive poster loop started at $(date -Iseconds)" >> "$LIVE_LOG" 

while true; do 
  RUN_ID="$(date +%Y%m%d_%H%M%S)" 
  RUN_LOG="$HOME_DIR/run_${RUN_ID}.log" 

  { 
    echo "===========================================================" 
    echo "RUN $RUN_ID" 
    echo "Time: $(date -Iseconds)" 
    echo "User: $(whoami)" 
    echo "Webhook set: $([ -n "${DISCORD_WEBHOOK_URL:-}" ] && echo YES || echo NO)" 
    echo 

    set -a 
    [ -f .env ] && source .env 
    set +a 

    echo "[0/3] Franchise sync + preflight:" 
    python services/sync_proactive_franchise_hints.py >/tmp/ai_nerd_franchise_sync.log 2>&1 || true
    tail -n 4 /tmp/ai_nerd_franchise_sync.log 2>/dev/null || true 
    python services/proactive_post_preflight.py || true 
    echo 

    echo "[1/3] Hourly social post:" 
    python services/proactive_referee_announcer.py --mode social || python services/proactive_referee_announcer.py --mode auto || true 
    echo 

    echo "[2/3] Staggered suggestion check:" 
    HOUR="$(date +%H)" 
    if [ $((10#$HOUR % 3)) -eq 0 ]; then 
      echo "Suggestion window is open." 
      python services/proactive_referee_announcer.py --mode suggest || true 
    else 
      echo "Suggestion window closed. Suggestions only run every 3 hours." 
    fi 
    echo 

    echo "[3/3] Status:" 
    { 
      echo "Last proactive check: $RUN_ID" 
      echo "Last log: $RUN_LOG" 
      echo "Updated: $(date -Iseconds)" 
    } > "$STATUS" 
    cat "$STATUS" 

    echo 
    echo "Completed: $(date -Iseconds)" 
  } | tee "$RUN_LOG" >> "$LIVE_LOG" 2>&1 

  sleep 3600 
done 
