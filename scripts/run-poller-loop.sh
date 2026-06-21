#!/usr/bin/env sh
set -eu

interval="${EMAIL_POLL_INTERVAL_SECONDS:-600}"
state_file="${EMAIL_POLL_STATE_FILE:-/tmp/email-poller-state.json}"

while true; do
  date -u +"poll_cycle_started_at=%Y-%m-%dT%H:%M:%SZ"
  python3 /app/scripts/poll-email.py --env-file /app/.env --state-file "$state_file"
  date -u +"poll_cycle_finished_at=%Y-%m-%dT%H:%M:%SZ"
  sleep "$interval"
done
