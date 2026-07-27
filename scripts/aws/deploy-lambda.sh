#!/usr/bin/env bash
# Build the poller zip and roll it onto the Lambda function. Replaces deploy-image.sh
# (ECR build + EKS rollout) after the serverless migration.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
region="${AWS_REGION:-us-east-1}"
function_name="${LAMBDA_FUNCTION_NAME:-priority-email-poller}"
zip="$root_dir/dist/priority-email-lambda.zip"

bash "$root_dir/scripts/aws/build-lambda-zip.sh" "$zip"

aws lambda update-function-code \
  --function-name "$function_name" \
  --zip-file "fileb://$zip" \
  --region "$region" \
  --publish >/dev/null
aws lambda wait function-updated --function-name "$function_name" --region "$region"

echo "deployed $function_name from $zip"
