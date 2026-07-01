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

# Use a local AWS profile when one is configured (operator workflow); fall
# back to the ambient credential chain (e.g. GitHub Actions OIDC) otherwise.
run_aws() {
  if [[ -n "$profile" ]]; then
    aws --profile "$profile" "$@"
  else
    aws "$@"
  fi
}

if ! run_aws ecr describe-repositories \
  --repository-names "$repo_name" \
  --region "$region" >/dev/null 2>&1; then
  run_aws ecr create-repository \
    --repository-name "$repo_name" \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    --tags Key=Application,Value=priority-email Key=Service,Value=priority-email Key=Stack,Value=ecr \
    --region "$region" >/dev/null
fi

run_aws ecr put-image-tag-mutability \
  --repository-name "$repo_name" \
  --image-tag-mutability MUTABLE \
  --region "$region" >/dev/null

run_aws ecr describe-repositories \
  --repository-names "$repo_name" \
  --region "$region" \
  --query 'repositories[0].repositoryUri' \
  --output text
