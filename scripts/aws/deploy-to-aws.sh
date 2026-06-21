#!/usr/bin/env bash
set -euo pipefail

scripts/aws/sync-runtime-secret.sh .env
image_uri="$(scripts/aws/build-and-push-image.sh | tee /dev/stderr | tail -n 1)"
if [[ "$image_uri" != *.dkr.ecr.*.amazonaws.com/priority-email-service:* ]]; then
  echo "Unexpected image URI from build: $image_uri" >&2
  exit 1
fi
SKIP_INITIAL_ROLLOUT_STATUS=true scripts/kubernetes/apply-manifests.sh
kubectl -n priority-email set image deployment/priority-email-service "priority-email-service=$image_uri"
kubectl -n priority-email rollout status deployment/priority-email-service --timeout=180s
