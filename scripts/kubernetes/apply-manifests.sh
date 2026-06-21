#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest_dir="$root_dir/infra/k8s"
env_file="${ENV_FILE:-$root_dir/.env}"
namespace="priority-email"

required_filters=(
  "$root_dir/filters/domain-filters.txt"
  "$root_dir/filters/email-address-filters.txt"
  "$root_dir/filters/sender-name-filters.txt"
)

for path in "${required_filters[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing filter file: $path" >&2
    exit 1
  fi
done

if [[ ! -f "$env_file" ]]; then
  echo "Missing env file: $env_file" >&2
  exit 1
fi

kubectl apply -f "$manifest_dir/namespace.yaml"
kubectl apply -f "$manifest_dir/serviceaccount.yaml"

kubectl -n "$namespace" create secret generic priority-email-secrets \
  --from-env-file="$env_file" \
  --dry-run=client \
  -o yaml | kubectl apply -f -

kubectl -n "$namespace" create configmap priority-email-filters \
  --from-file=domain-filters.txt="$root_dir/filters/domain-filters.txt" \
  --from-file=email-address-filters.txt="$root_dir/filters/email-address-filters.txt" \
  --from-file=sender-name-filters.txt="$root_dir/filters/sender-name-filters.txt" \
  --dry-run=client \
  -o yaml | kubectl apply -f -

kubectl apply -f "$manifest_dir/network-policy.yaml"
kubectl apply -f "$manifest_dir/deployment.yaml"
kubectl apply -f "$manifest_dir/poddisruptionbudget.yaml"

kubectl -n "$namespace" rollout status deployment/priority-email-service --timeout=180s
