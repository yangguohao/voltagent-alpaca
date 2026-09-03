#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

if pgrep -f "python scripts/run_agent.py --mode daemon" >/dev/null 2>&1; then
  echo "Stopping existing daemon..."
  pkill -f "python scripts/run_agent.py --mode daemon" || true
  sleep 1
fi

nohup env PYTHONPATH=. python scripts/run_agent.py --mode daemon --live >> logs/agent.log 2>&1 &
echo $! > logs/agent.pid
echo "Agent daemon started (pid=$(cat logs/agent.pid))"
echo "Logs: $ROOT/logs/agent.log"
