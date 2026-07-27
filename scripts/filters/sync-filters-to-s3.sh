#!/usr/bin/env bash
# Deploy-side filter sync (serverless): decrypt the committed filter ops log, assemble the
# plaintext filter files in a temp dir, upload them to the poller's S3 state/filters bucket,
# and verify each object by checksum. Never prints filter values. Replaces the former
# ConfigMap-based sync-filters-from-ops.sh after the EKS->Lambda migration.
#
# Requires: STATE_BUCKET env var, aws CLI creds, the age key (AGE_SECRET_KEY) for decrypt.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bucket="${STATE_BUCKET:?STATE_BUCKET is required}"

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

"$root_dir/scripts/filters/decrypt-filters.sh" "$work_dir"

sha256() {
  python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
}

failures=0
for name in domain-filters.txt email-address-filters.txt sender-name-filters.txt; do
  aws s3 cp "$work_dir/$name" "s3://$bucket/filters/$name" --only-show-errors
  local_sum="$(sha256 "$work_dir/$name")"
  live_sum="$(aws s3 cp "s3://$bucket/filters/$name" - | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
  if [[ "$local_sum" == "$live_sum" ]]; then
    echo "verified $name: live S3 object matches assembled filters"
  else
    echo "MISMATCH $name: live S3 object does not match assembled filters" >&2
    failures=1
  fi
done
exit "$failures"
