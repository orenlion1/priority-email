#!/usr/bin/env bash
# Deploy-side filter sync: decrypt the committed filter ops log, assemble the
# plaintext filter files in a temp dir, apply the priority-email-filters
# ConfigMap, restart the poller deployment, and verify the live ConfigMap by
# checksum. Never prints filter values. Intended for the Deploy workflow but
# also runnable by an operator with cluster access and the age key.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
namespace="priority-email"

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

"$root_dir/scripts/filters/decrypt-filters.sh" "$work_dir"

kubectl -n "$namespace" create configmap priority-email-filters \
  --from-file=domain-filters.txt="$work_dir/domain-filters.txt" \
  --from-file=email-address-filters.txt="$work_dir/email-address-filters.txt" \
  --from-file=sender-name-filters.txt="$work_dir/sender-name-filters.txt" \
  --dry-run=client \
  -o yaml | kubectl apply -f -

kubectl -n "$namespace" rollout restart deployment/priority-email-service
kubectl -n "$namespace" rollout status deployment/priority-email-service --timeout=180s

failures=0
for name in domain-filters.txt email-address-filters.txt sender-name-filters.txt; do
  local_sum="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$work_dir/$name")"
  live_sum="$(kubectl -n "$namespace" get configmap priority-email-filters -o go-template="{{index .data \"$name\"}}" | python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
  if [[ "$local_sum" == "$live_sum" ]]; then
    echo "verified $name: live ConfigMap matches assembled filters"
  else
    echo "MISMATCH $name: live ConfigMap does not match assembled filters" >&2
    failures=1
  fi
done
exit "$failures"
