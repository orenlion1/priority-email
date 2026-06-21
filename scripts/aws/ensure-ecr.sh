#!/usr/bin/env bash
set -euo pipefail

env_file="${ENV_FILE:-.env}"
repo_name="${ECR_REPOSITORY_NAME:-priority-email-service}"

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
: "${profile:?Set AWS_PROFILE in your local .env or shell.}"

if ! aws ecr describe-repositories \
  --repository-names "$repo_name" \
  --region "$region" \
  --profile "$profile" >/dev/null 2>&1; then
  aws ecr create-repository \
    --repository-name "$repo_name" \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    --tags Key=Application,Value=priority-email Key=Service,Value=priority-email Key=Stack,Value=ecr \
    --region "$region" \
    --profile "$profile" >/dev/null
fi

aws ecr put-image-tag-mutability \
  --repository-name "$repo_name" \
  --image-tag-mutability MUTABLE \
  --region "$region" \
  --profile "$profile" >/dev/null

aws ecr describe-repositories \
  --repository-names "$repo_name" \
  --region "$region" \
  --profile "$profile" \
  --query 'repositories[0].repositoryUri' \
  --output text
