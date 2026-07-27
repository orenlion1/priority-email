#!/usr/bin/env bash
# Operator bootstrap (serverless). Syncs the runtime secret to Secrets Manager, which the
# Lambda reads at each poll cycle. Everything else — the Lambda, S3 state/filters bucket,
# EventBridge schedule, and IAM — is provisioned by infra/terraform. Filter values ship via
# the GitHub Actions Deploy workflow (encrypted ops -> S3) and are NOT applied here.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${ENV_FILE:-$root_dir/.env}"

"$root_dir/scripts/aws/sync-runtime-secret.sh" "$env_file"

echo "Runtime secret synced to Secrets Manager (priority-email/runtime)."
echo "Provision or update infra with: terraform -chdir=infra/terraform apply"
