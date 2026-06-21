#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
secret_name="${AWS_SECRET_NAME:-priority-email/runtime}"
region="${AWS_REGION:-us-east-1}"
profile="${AWS_PROFILE:-ensemble-grafana}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing env file: $env_file" >&2
  exit 1
fi

if aws secretsmanager describe-secret \
  --secret-id "$secret_name" \
  --region "$region" \
  --profile "$profile" >/dev/null 2>&1; then
  aws secretsmanager put-secret-value \
    --secret-id "$secret_name" \
    --secret-string "file://$env_file" \
    --region "$region" \
    --profile "$profile" >/dev/null
else
  aws secretsmanager create-secret \
    --name "$secret_name" \
    --description "Priority Email runtime configuration" \
    --secret-string "file://$env_file" \
    --tags Key=Application,Value=priority-email Key=Service,Value=priority-email Key=Stack,Value=runtime \
    --region "$region" \
    --profile "$profile" >/dev/null
fi

echo "$secret_name"
