#!/usr/bin/env bash
set -euo pipefail

scripts/aws/sync-runtime-secret.sh .env
image_uri="$(scripts/aws/build-and-push-image.sh)"
scripts/kubernetes/apply-manifests.sh
kubectl -n priority-email set image deployment/priority-email-service "priority-email-service=$image_uri"
kubectl -n priority-email rollout status deployment/priority-email-service --timeout=180s
