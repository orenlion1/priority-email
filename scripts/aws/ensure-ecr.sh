#!/usr/bin/env bash
set -euo pipefail

repo_name="${ECR_REPOSITORY_NAME:-priority-email-service}"
region="${AWS_REGION:-us-east-1}"
profile="${AWS_PROFILE:?Set AWS_PROFILE in your local .env or shell.}"

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
