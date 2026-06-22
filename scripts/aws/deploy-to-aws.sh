#!/usr/bin/env bash
set -euo pipefail

env_file="${ENV_FILE:-.env}"

env_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

export AWS_REGION="${AWS_REGION:-$(env_value AWS_REGION)}"
export AWS_PROFILE="${AWS_PROFILE:-$(env_value AWS_PROFILE)}"
export AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(env_value AWS_ACCOUNT_ID)}"

scripts/aws/sync-runtime-secret.sh "$env_file"
scripts/aws/ensure-ebs-csi-addon.sh "$env_file" >/dev/stderr
image_uri="$(scripts/aws/build-and-push-image.sh | tee /dev/stderr | tail -n 1)"
if [[ "$image_uri" != *.dkr.ecr.*.amazonaws.com/priority-email-service:* ]]; then
  echo "Unexpected image URI from build: $image_uri" >&2
  exit 1
fi
SKIP_INITIAL_ROLLOUT_STATUS=true scripts/kubernetes/apply-manifests.sh
kubectl -n priority-email set image deployment/priority-email-service "priority-email-service=$image_uri"
kubectl -n priority-email rollout status deployment/priority-email-service --timeout=180s
