#!/usr/bin/env bash
# Build the Slack events zip and roll it onto the Lambda function. The infra
# stack (infra/slack.tf) creates the function with a placeholder and ignores
# code changes; this owns the code, exactly as deploy-lambda.sh does for the
# poller.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
region="${AWS_REGION:-us-east-1}"
function_name="${SLACK_LAMBDA_FUNCTION_NAME:-priority-email-slack-events}"
zip="$root_dir/dist/priority-email-slack-lambda.zip"

bash "$root_dir/scripts/aws/build-slack-lambda-zip.sh" "$zip"

aws lambda update-function-code \
  --function-name "$function_name" \
  --zip-file "fileb://$zip" \
  --region "$region" \
  --publish >/dev/null
aws lambda wait function-updated --function-name "$function_name" --region "$region"

echo "deployed $function_name from $zip"
