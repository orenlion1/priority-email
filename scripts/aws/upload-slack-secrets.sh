#!/usr/bin/env bash
#
# Upload priority-email's Slack app credentials (signing secret + bot token) into
# their Secrets Manager containers, which the events handler reads at runtime.
#
# These are priority-email's OWN Slack app credentials (a SEPARATE app from
# re-rank), so they cannot be reused from re-rank's secrets — retrieve them from
# https://api.slack.com/apps and either put them in slack-secrets.env (see
# slack-secrets.env.example) or let the script prompt for them.
#
#   ./upload-slack-secrets.sh            # write the values, then verify them
#   ./upload-slack-secrets.sh --check    # report what's stored/valid, change nothing
#
# Safety properties (this handles live credentials):
#   - Fails closed on identity: refuses unless the profile resolves to the
#     expected account before any write.
#   - Validates the shape of each value and re-prompts (interactive) or exits
#     (file/piped) rather than storing something malformed.
#   - Never puts a secret on the command line, in the shell history, or in the
#     process list — values move over stdin / a 0600 temp file only.
#   - Verifies the OUTCOME, not just the write: re-reads each stored value and
#     exercises the bot token against Slack's auth.test.
#   - Idempotent: a value already stored correctly is left untouched.

set -euo pipefail

# --- Fixed configuration -----------------------------------------------------
PROFILE="ensemble-grafana"
REGION="us-east-1"
SIGNING_SECRET_ID="priority-email/slack-signing-secret"
BOT_TOKEN_ID="priority-email/slack-bot-token"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR%/scripts/aws}"
ENV_FILE="${SCRIPT_DIR}/slack-secrets.env"

# The expected account is resolved at runtime, never committed (repo policy keeps
# real identifiers out of tracked files — the CI secret scan fails on them).
# Order: PRIORITY_EMAIL_ACCOUNT_ID env var, then AWS_ACCOUNT_ID in the gitignored
# .env. The fail-closed identity check below refuses to write without it.
EXPECTED_ACCOUNT="${PRIORITY_EMAIL_ACCOUNT_ID:-}"
if [[ -z "$EXPECTED_ACCOUNT" && -f "${REPO_ROOT}/.env" ]]; then
  EXPECTED_ACCOUNT="$(grep -E '^AWS_ACCOUNT_ID=' "${REPO_ROOT}/.env" | tail -n 1 | cut -d= -f2- | tr -d "\"' " || true)"
fi

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1
if [[ -n "${1:-}" && "${1:-}" != "--check" ]]; then
  echo "usage: $(basename "$0") [--check]" >&2
  exit 2
fi

# --- Helpers -----------------------------------------------------------------
die() { echo "ERROR: $*" >&2; exit 1; }
note() { echo "  $*"; }
aws_cli() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

# Read one KEY's value from the env file without sourcing it (no code execution).
from_env_file() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  [[ -z "$line" ]] && return 0
  line="${line#"${key}"=}"
  line="${line%\"}"; line="${line#\"}"
  line="${line%\'}"; line="${line#\'}"
  printf '%s' "$line"
}

valid_signing() { [[ "$1" =~ ^[0-9a-f]{32}$ ]]; }
valid_bot()     { [[ "$1" =~ ^xoxb-[A-Za-z0-9-]+$ ]]; }

# Current stored value of a secret, or "" if the container has no version yet.
stored_value() {
  aws_cli secretsmanager get-secret-value --secret-id "$1" \
    --query SecretString --output text 2>/dev/null || true
}

# Store a value via stdin so it never reaches argv / ps / history.
put_value() {
  local id="$1" value="$2"
  printf '%s' "$value" \
    | aws_cli secretsmanager put-secret-value \
        --secret-id "$id" --secret-string file:///dev/stdin >/dev/null
}

# Exercise the bot token against the real Slack API. Echoes "ok <team>/<user>"
# on success; returns non-zero and echoes the Slack error otherwise. The token
# goes to curl via a 0600 temp header file, never on the command line.
verify_bot_token() {
  local token="$1" hdr resp
  hdr="$(mktemp)"; chmod 600 "$hdr"
  printf 'Authorization: Bearer %s' "$token" > "$hdr"
  resp="$(curl -s --max-time 20 -H "@$hdr" https://slack.com/api/auth.test || true)"
  rm -f "$hdr"
  if printf '%s' "$resp" | grep -q '"ok":[[:space:]]*true'; then
    local team user
    team="$(printf '%s' "$resp" | sed -n 's/.*"team":"\([^"]*\)".*/\1/p')"
    user="$(printf '%s' "$resp" | sed -n 's/.*"user":"\([^"]*\)".*/\1/p')"
    printf 'ok %s/%s' "${team:-?}" "${user:-?}"
    return 0
  fi
  printf '%s' "$resp" | sed -n 's/.*"error":"\([^"]*\)".*/\1/p'
  return 1
}

# Prompt for a value interactively, validating with up to 3 retries.
prompt_secret() {
  local label="$1" validator="$2" __out="$3" val tries=0
  while (( tries < 3 )); do
    val=""; read -rs -p "  $label: " val < /dev/tty || true; echo >&2
    if "$validator" "$val"; then printf -v "$__out" '%s' "$val"; return 0; fi
    echo "  value doesn't look right (got length ${#val}); try again" >&2
    (( ++tries ))
  done
  die "$label: 3 invalid attempts, aborting"
}

# --- Preflight: identity (fail closed) ---------------------------------------
echo "Profile: $PROFILE  Region: $REGION"
[[ -n "$EXPECTED_ACCOUNT" ]] || die "expected account id unknown — set PRIORITY_EMAIL_ACCOUNT_ID or AWS_ACCOUNT_ID in ${REPO_ROOT}/.env so identity can be checked before writing"
account="$(aws_cli sts get-caller-identity --query Account --output text 2>/dev/null || true)"
[[ -n "$account" ]] || die "could not authenticate with profile '$PROFILE' — run 'aws sso login --profile $PROFILE' (or configure it) and retry"
[[ "$account" == "$EXPECTED_ACCOUNT" ]] || die "profile '$PROFILE' resolves to account $account, expected $EXPECTED_ACCOUNT — refusing to touch secrets"
note "identity ok (account $account)"

# --- Preflight: containers exist (don't instruct a step with no prerequisite) -
for id in "$SIGNING_SECRET_ID" "$BOT_TOKEN_ID"; do
  aws_cli secretsmanager describe-secret --secret-id "$id" >/dev/null 2>&1 \
    || die "secret container '$id' does not exist — apply infra/terraform (slack.tf) first"
done
note "both secret containers present"
echo

# --- --check: report and exit, changing nothing ------------------------------
if (( CHECK_ONLY )); then
  echo "Checking stored values (no changes):"
  sv="$(stored_value "$SIGNING_SECRET_ID")"
  if [[ -z "$sv" ]]; then note "signing secret: NOT SET"
  elif valid_signing "$sv"; then note "signing secret: set, shape ok (32 hex)"
  else note "signing secret: set but shape looks wrong (length ${#sv})"; fi

  bt="$(stored_value "$BOT_TOKEN_ID")"
  if [[ -z "$bt" ]]; then note "bot token: NOT SET"
  else
    if res="$(verify_bot_token "$bt")"; then note "bot token: set, VALID via auth.test ($res)"
    else note "bot token: set but Slack REJECTED it (error: ${res:-unknown})"; fi
  fi
  echo
  echo "Outstanding: any line above that says NOT SET / wrong / REJECTED."
  exit 0
fi

# --- Gather inputs -----------------------------------------------------------
SIGNING="$(from_env_file SLACK_SIGNING_SECRET)"
BOT="$(from_env_file SLACK_BOT_TOKEN)"

if [[ -n "$SIGNING" || -n "$BOT" ]]; then
  echo "Loaded values from ${ENV_FILE##*/}"
fi

# Fill any missing/invalid value by prompting, but only if we have a real TTY.
if ! valid_signing "${SIGNING:-}"; then
  [[ -n "${SIGNING:-}" ]] && echo "signing secret from file failed validation (length ${#SIGNING})" >&2
  if [[ -t 0 || -r /dev/tty ]]; then prompt_secret "Signing Secret (32 hex)" valid_signing SIGNING
  else die "no valid SLACK_SIGNING_SECRET (set it in $ENV_FILE or run interactively)"; fi
fi
if ! valid_bot "${BOT:-}"; then
  [[ -n "${BOT:-}" ]] && echo "bot token from file failed validation (prefix '${BOT:0:5}')" >&2
  if [[ -t 0 || -r /dev/tty ]]; then prompt_secret "Bot User OAuth Token (xoxb-...)" valid_bot BOT
  else die "no valid SLACK_BOT_TOKEN (set it in $ENV_FILE or run interactively)"; fi
fi

# --- Verify the bot token BEFORE storing (a revoked key must fail loudly) -----
echo "Validating bot token against Slack..."
if res="$(verify_bot_token "$BOT")"; then note "auth.test ok ($res)"
else die "Slack rejected the bot token (error: ${res:-unknown}) — nothing written"; fi

# --- Write (idempotent), then verify the stored outcome ----------------------
echo "Storing values:"
for pair in "signing:$SIGNING_SECRET_ID:$SIGNING" "bot:$BOT_TOKEN_ID:$BOT"; do
  kind="${pair%%:*}"; rest="${pair#*:}"; id="${rest%%:*}"; val="${rest#*:}"
  if [[ "$(stored_value "$id")" == "$val" ]]; then
    note "$id: already up to date, skipping"
    continue
  fi
  put_value "$id" "$val"
  # Verify the write landed by re-reading (length only — never print the value).
  if [[ "$(stored_value "$id")" == "$val" ]]; then
    note "$id: stored and re-read ok (length ${#val})"
  else
    die "$id: wrote a value but read back something different — investigate"
  fi
done

# --- Known gaps / next steps -------------------------------------------------
echo
echo "Done. Notes:"
note "The signing secret is stored and shape-valid, but can only be fully"
note "confirmed by a real signed Slack request — set the Event Subscriptions"
note "Request URL and watch for a green 'Verified' in the Slack app config."
note "The handler reads secrets per invocation, so this takes effect on the"
note "next request — no redeploy needed."
if [[ -f "$ENV_FILE" ]]; then
  note "Shred the local file now:  rm -P '$ENV_FILE'   (or: shred -u on Linux)"
fi
