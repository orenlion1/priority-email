#!/usr/bin/env bash
# Append an encrypted filter operation to filters/ops/. Requires only the
# committed age public key, so any coding agent or operator can add or remove
# a filter without ever seeing existing filter values.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
recipients="$root_dir/filters/age-recipients.pub"
ops_dir="$root_dir/filters/ops"

usage() {
  echo "usage: $0 <add|remove> <domain|email-address|sender-name> <value>" >&2
  exit 1
}

[[ $# -eq 3 ]] || usage
action="$1"
kind="$2"
value="$3"

case "$action" in
  add|remove) ;;
  *) usage ;;
esac
case "$kind" in
  domain|email-address|sender-name) ;;
  *) usage ;;
esac

if ! command -v age >/dev/null 2>&1; then
  echo "age is required (brew install age / apt-get install age)" >&2
  exit 1
fi
if [[ ! -f "$recipients" ]]; then
  echo "Missing age recipients file: $recipients" >&2
  exit 1
fi

op_json="$(python3 -c 'import json, sys; print(json.dumps({"action": sys.argv[1], "kind": sys.argv[2], "value": sys.argv[3]}))' "$action" "$kind" "$value")"

# Dry-run the operation through the assembler so an invalid value is rejected
# before it is encrypted and committed.
validate_dir="$(mktemp -d)"
trap 'rm -rf "$validate_dir"' EXIT
printf '%s\n' "$op_json" | python3 "$root_dir/scripts/filters/assemble-filters.py" --output-dir "$validate_dir" >/dev/null

mkdir -p "$ops_dir"
op_name="$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import secrets; print(secrets.token_hex(3))').age"
printf '%s\n' "$op_json" | age --encrypt -R "$recipients" -a -o "$ops_dir/$op_name"

echo "Encrypted filter op written: filters/ops/$op_name"
echo "Commit and push it to main; the Deploy workflow syncs the live ConfigMap."
