#!/usr/bin/env bash
# Run the sync from cron. Use absolute paths so it works when run by cron.
# Example crontab (every 12 hours at 0:00 and 12:00):
#   0 */12 * * * /path/to/agentic-opscopilot/scripts/run_sync_cron.sh >> /tmp/opscopilot_sync.log 2>&1

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Load .env if present (no overwrite of existing env)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1090
  source .env
  set +a
fi

# Use project venv if it exists
if [ -d "$PROJECT_ROOT/.venv/bin" ]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [ -d "$PROJECT_ROOT/venv/bin" ]; then
  PYTHON="$PROJECT_ROOT/venv/bin/python"
elif [ -n "$VIRTUAL_ENV" ]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
else
  PYTHON=python3
fi

exec "$PYTHON" -m app.run_sync
