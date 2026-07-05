#!/usr/bin/env bash
# Decrypt the filter ops log and assemble plaintext filter files into the
# given directory (defaults to the gitignored filters/ directory). Requires
# the age identity: AGE_SECRET_KEY env var, or AGE_KEY_FILE, or the default
# operator key at ~/.config/priority-email/age.key.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ops_dir="$root_dir/filters/ops"
output_dir="${1:-$root_dir/filters}"

if ! command -v age >/dev/null 2>&1; then
  echo "age is required (brew install age / apt-get install age)" >&2
  exit 1
fi

key_file="${AGE_KEY_FILE:-$HOME/.config/priority-email/age.key}"
temp_key=""
cleanup() {
  if [[ -n "$temp_key" ]]; then
    rm -f "$temp_key"
  fi
}
trap cleanup EXIT
if [[ -n "${AGE_SECRET_KEY:-}" ]]; then
  temp_key="$(mktemp)"
  chmod 600 "$temp_key"
  printf '%s\n' "$AGE_SECRET_KEY" > "$temp_key"
  key_file="$temp_key"
fi
if [[ ! -f "$key_file" ]]; then
  echo "Missing age identity (set AGE_SECRET_KEY or AGE_KEY_FILE)" >&2
  exit 1
fi

shopt -s nullglob
op_files=("$ops_dir"/*.age)
if [[ ${#op_files[@]} -eq 0 ]]; then
  echo "No encrypted filter ops found in filters/ops/" >&2
  exit 1
fi

# Glob expansion is lexicographic, which matches chronological order for the
# timestamp-prefixed op filenames.
for op_file in "${op_files[@]}"; do
  age --decrypt -i "$key_file" "$op_file"
done | python3 "$root_dir/scripts/filters/assemble-filters.py" --output-dir "$output_dir"
