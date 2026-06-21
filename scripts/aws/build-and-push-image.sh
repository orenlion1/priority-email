#!/usr/bin/env bash
set -euo pipefail

region="${AWS_REGION:-us-east-1}"
profile="${AWS_PROFILE:?Set AWS_PROFILE in your local .env or shell.}"
account_id="${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID in your local .env or shell.}"
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
