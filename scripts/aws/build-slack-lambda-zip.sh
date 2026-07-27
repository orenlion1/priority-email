#!/usr/bin/env bash
# Build the Lambda deployment zip for the priority-email Slack events handler.
#
# Unlike the poller (stdlib-only), the handler needs two things bundled that are
# not in the Lambda runtime:
#   - slackkit, the shared Slack command-bot core, from the private CodeArtifact
#     repository;
#   - the `age` binary, to append an encrypted filter op with the public
#     recipients key (scripts/slack/filter_store.py shells to it), plus the
#     committed public key at filters/age-recipients.pub.
#
# Handler entry point: scripts/slack/slack_handler.py -> handler =
# "scripts.slack.slack_handler.handler". slackkit installs at the zip root so it
# imports as `slackkit`; `age` sits at the root and Terraform sets
# AGE_BIN=/var/task/age.
#
# Required env: CODEARTIFACT_DOMAIN, CODEARTIFACT_REPOSITORY, AWS_ACCOUNT_ID.
# Optional: AGE_VERSION (pinned below), AWS_REGION.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="${1:-$root_dir/dist/priority-email-slack-lambda.zip}"
region="${AWS_REGION:-us-east-1}"

# CodeArtifact coordinates default to the shared repo the CI already uses
# (domain "orenlion1", repo "python"; see .github/workflows/ci.yml). slackkit is
# published there and read via the slackkit-reader OIDC role.
CODEARTIFACT_DOMAIN="${CODEARTIFACT_DOMAIN:-orenlion1}"
CODEARTIFACT_REPOSITORY="${CODEARTIFACT_REPOSITORY:-python}"
: "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}"

# age release pinned by version and checksum: a Lambda that shells to an
# unverified binary is a supply-chain hole. The checksum is intentionally NOT
# hardcoded to a guessed value -- set AGE_SHA256 to the published
# age-vX-linux-amd64.tar.gz SHA-256 (from the release's checksums file) so the
# build fails closed until a real, verified value is supplied.
age_version="${AGE_VERSION:-1.2.1}"
age_sha256="${AGE_SHA256:-}"
if [ -z "$age_sha256" ]; then
  echo "AGE_SHA256 is required: the SHA-256 of age-v${age_version}-linux-amd64.tar.gz." >&2
  echo "Find it in the release checksums at https://github.com/FiloSottile/age/releases/tag/v${age_version}" >&2
  exit 1
fi

build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
mkdir -p "$(dirname "$out")"
rm -f "$out"

# --- slackkit from CodeArtifact ------------------------------------------------
token="$(aws codeartifact get-authorization-token \
  --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$AWS_ACCOUNT_ID" \
  --region "$region" --query authorizationToken --output text)"
endpoint="$(aws codeartifact get-repository-endpoint \
  --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$AWS_ACCOUNT_ID" \
  --repository "$CODEARTIFACT_REPOSITORY" --format pypi \
  --region "$region" --query repositoryEndpoint --output text)"

python3 -m pip install --quiet --upgrade \
  --index-url "https://aws:${token}@${endpoint#https://}simple/" \
  --target "$build_dir" slackkit

# --- age binary (verified) -----------------------------------------------------
age_tgz="$build_dir/age.tar.gz"
curl -fsSL -o "$age_tgz" \
  "https://github.com/FiloSottile/age/releases/download/v${age_version}/age-v${age_version}-linux-amd64.tar.gz"
echo "${age_sha256}  ${age_tgz}" | sha256sum -c -
tar -xzf "$age_tgz" -C "$build_dir" --strip-components=1 age/age
rm -f "$age_tgz"
chmod +x "$build_dir/age"

# --- application source + committed public key --------------------------------
cp -R "$root_dir/scripts" "$build_dir/scripts"
mkdir -p "$build_dir/filters"
cp "$root_dir/filters/age-recipients.pub" "$build_dir/filters/age-recipients.pub"

# --- package -------------------------------------------------------------------
( cd "$build_dir" && zip -r -q "$out" . \
    -x '*/__pycache__/*' -x '*.pyc' -x '*.dist-info/*' )

echo "built $out ($(wc -c <"$out") bytes)"
