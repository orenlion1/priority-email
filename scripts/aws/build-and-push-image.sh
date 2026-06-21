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

region="${AWS_REGION:-$(env_value AWS_REGION)}"
region="${region:-us-east-1}"
profile="${AWS_PROFILE:-$(env_value AWS_PROFILE)}"
account_id="${AWS_ACCOUNT_ID:-$(env_value AWS_ACCOUNT_ID)}"
: "${profile:?Set AWS_PROFILE in your local .env or shell.}"
: "${account_id:?Set AWS_ACCOUNT_ID in your local .env or shell.}"
repo_name="${ECR_REPOSITORY_NAME:-priority-email-service}"
tag="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
image_uri="$account_id.dkr.ecr.$region.amazonaws.com/$repo_name:$tag"
latest_uri="$account_id.dkr.ecr.$region.amazonaws.com/$repo_name:latest"

repository_uri="$(scripts/aws/ensure-ecr.sh)"

aws ecr get-login-password --region "$region" --profile "$profile" \
  | docker login --username AWS --password-stdin "$account_id.dkr.ecr.$region.amazonaws.com" >/dev/null

docker build --platform linux/amd64 -t "$image_uri" -t "$latest_uri" .
docker push "$image_uri"
docker push "$latest_uri"

echo "$repository_uri:$tag"
