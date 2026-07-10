#!/usr/bin/env bash
# Build the Lambda deployment zip for the Priority Email poller.
#
# The poller is stdlib-only (its sole third-party need, boto3, ships in the Lambda
# runtime), so the package is just the scripts/ tree. Handler entry point is
# scripts/aws/lambda_function.py -> handler = "scripts.aws.lambda_function.handler"
# (scripts and scripts/aws resolve as Python 3 namespace packages under /var/task).
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="${1:-$root_dir/dist/priority-email-lambda.zip}"

mkdir -p "$(dirname "$out")"
rm -f "$out"

cd "$root_dir"
# Exclude caches and local runtime artifacts; ship only source.
zip -r -q "$out" scripts \
  -x 'scripts/**/__pycache__/*' \
  -x '*.pyc'

echo "built $out ($(wc -c <"$out") bytes)"
