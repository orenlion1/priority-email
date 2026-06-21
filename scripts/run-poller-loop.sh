#!/usr/bin/env sh
set -eu

interval="${EMAIL_POLL_INTERVAL_SECONDS:-600}"
state_file="${EMAIL_POLL_STATE_FILE:-/tmp/email-poller-state.json}"
log_level="$(printf '%s' "${EMAIL_LOG_LEVEL:-${LOG_LEVEL:-INFO}}" | tr '[:lower:]' '[:upper:]')"

log_info() {
  case "$log_level" in
    DEBUG|INFO)
      timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
      printf '{"timestamp":"%s","level":"INFO","service":"priority-email-service","event":"%s"}\n' "$timestamp" "$1"
      ;;
  esac
}

while true; do
  log_info "poll_cycle_started"
  python3 /app/scripts/poll-email.py --env-file /app/.env --state-file "$state_file"
  log_info "poll_cycle_finished"
  sleep "$interval"
done
