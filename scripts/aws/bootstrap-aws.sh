#!/usr/bin/env bash
# Operator bootstrap for secrets and infrastructure. Image rollout and filter
# delivery are owned by the GitHub Actions Deploy workflow and are NOT done
# here: this script only syncs the runtime secret, ensures the EBS CSI
# add-on, and applies the Kubernetes manifests. When a live ECR image is
# already deployed it is preserved across the manifest apply.
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

namespace="priority-email"
deployment="priority-email-service"

scripts/aws/sync-runtime-secret.sh "$env_file"
scripts/aws/ensure-ebs-csi-addon.sh "$env_file" >/dev/stderr

# The committed deployment manifest carries a placeholder image. Remember the
# currently deployed image so reapplying manifests never rolls a live
# deployment back to the placeholder.
current_image="$(kubectl -n "$namespace" get "deployment/$deployment" \
  -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"

SKIP_INITIAL_ROLLOUT_STATUS=true scripts/kubernetes/apply-manifests.sh

if [[ "$current_image" == *.dkr.ecr.*.amazonaws.com/* ]]; then
  kubectl -n "$namespace" set image "deployment/$deployment" "$deployment=$current_image"
  kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=180s
else
  echo "No previously deployed ECR image found. Roll out an image via the" >&2
  echo "Deploy workflow (push an image-affecting commit to main, or rerun" >&2
  echo "the latest successful Deploy run with 'gh run rerun')." >&2
fi
