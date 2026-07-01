#!/usr/bin/env bash
set -euo pipefail

# Continuous-deployment image rollout for priority-email-service.
#
# Builds and pushes the current commit's image to ECR, then updates the
# running Kubernetes deployment and waits for the rollout to finish. This is
# the automated path used by GitHub Actions after CI passes, using AWS
# credentials from the environment (OIDC) rather than a local profile.
#
# Runtime secrets, filter ConfigMaps, and infrastructure add-ons are managed
# separately by operators via scripts/aws/deploy-to-aws.sh and are not
# touched here.

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
namespace="priority-email"
deployment="priority-email-service"

image_uri="$("$root_dir/scripts/aws/build-and-push-image.sh" | tee /dev/stderr | tail -n 1)"
if [[ "$image_uri" != *.dkr.ecr.*.amazonaws.com/priority-email-service:* ]]; then
  echo "Unexpected image URI from build: $image_uri" >&2
  exit 1
fi

kubectl -n "$namespace" set image "deployment/$deployment" "$deployment=$image_uri"
kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=180s
