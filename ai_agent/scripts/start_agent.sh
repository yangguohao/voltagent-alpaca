#!/usr/bin/env bash
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$AGENT_DIR/.." && pwd)"
cd "$ROOT"
mkdir -p ai_agent/logs

if pgrep -f "python ai_agent/scripts/run_agent.py --mode daemon" >/dev/null 2>&1; then
  echo "Stopping existing daemon..."
  pkill -f "python ai_agent/scripts/run_agent.py --mode daemon" || true
  sleep 1
fi

nohup env PYTHONPATH=. python ai_agent/scripts/run_agent.py --mode daemon --live >> ai_agent/logs/agent.log 2>&1 &
echo $! > ai_agent/logs/agent.pid
echo "Agent daemon started (pid=$(cat ai_agent/logs/agent.pid))"
echo "Logs: $ROOT/ai_agent/logs/agent.log"
