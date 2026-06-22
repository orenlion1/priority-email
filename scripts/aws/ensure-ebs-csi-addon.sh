#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-${ENV_FILE:-.env}}"

env_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

cluster_from_context() {
  local context
  context="$(kubectl config current-context)"
  printf '%s' "${context##*/}"
}

export AWS_REGION="${AWS_REGION:-$(env_value AWS_REGION)}"
export AWS_PROFILE="${AWS_PROFILE:-$(env_value AWS_PROFILE)}"
export AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(env_value AWS_ACCOUNT_ID)}"

cluster_name="${EKS_CLUSTER_NAME:-$(env_value EKS_CLUSTER_NAME)}"
cluster_name="${cluster_name:-$(cluster_from_context)}"
role_name="${EBS_CSI_DRIVER_ROLE_NAME:-$(env_value EBS_CSI_DRIVER_ROLE_NAME)}"
role_name="${role_name:-${cluster_name}-ebs-csi-driver}"

if [[ -z "$AWS_REGION" ]]; then
  echo "Missing AWS_REGION in environment or $env_file" >&2
  exit 1
fi
if [[ -z "$AWS_ACCOUNT_ID" ]]; then
  AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
fi

oidc_issuer="$(aws eks describe-cluster \
  --name "$cluster_name" \
  --region "$AWS_REGION" \
  --query 'cluster.identity.oidc.issuer' \
  --output text)"
oidc_hostpath="${oidc_issuer#https://}"
provider_arn="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/${oidc_hostpath}"

if ! aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn "$provider_arn" >/dev/null 2>&1; then
  echo "Missing IAM OIDC provider: $provider_arn" >&2
  echo "Create the EKS OIDC provider before enabling the EBS CSI add-on." >&2
  exit 1
fi

trust_policy="$(
  cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "${provider_arn}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "${oidc_hostpath}:aud": "sts.amazonaws.com",
          "${oidc_hostpath}:sub": "system:serviceaccount:kube-system:ebs-csi-controller-sa"
        }
      }
    }
  ]
}
JSON
)"

if ! role_arn="$(aws iam get-role --role-name "$role_name" --query 'Role.Arn' --output text 2>/dev/null)"; then
  role_arn="$(aws iam create-role \
    --role-name "$role_name" \
    --assume-role-policy-document "$trust_policy" \
    --query 'Role.Arn' \
    --output text)"
else
  aws iam update-assume-role-policy \
    --role-name "$role_name" \
    --policy-document "$trust_policy" >/dev/null
fi

aws iam attach-role-policy \
  --role-name "$role_name" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy >/dev/null

if aws eks describe-addon \
  --cluster-name "$cluster_name" \
  --region "$AWS_REGION" \
  --addon-name aws-ebs-csi-driver >/dev/null 2>&1; then
  current_role="$(aws eks describe-addon \
    --cluster-name "$cluster_name" \
    --region "$AWS_REGION" \
    --addon-name aws-ebs-csi-driver \
    --query 'addon.serviceAccountRoleArn' \
    --output text)"
  if [[ "$current_role" != "$role_arn" ]]; then
    aws eks update-addon \
      --cluster-name "$cluster_name" \
      --region "$AWS_REGION" \
      --addon-name aws-ebs-csi-driver \
      --service-account-role-arn "$role_arn" \
      --resolve-conflicts OVERWRITE >/dev/null
  fi
else
  aws eks create-addon \
    --cluster-name "$cluster_name" \
    --region "$AWS_REGION" \
    --addon-name aws-ebs-csi-driver \
    --service-account-role-arn "$role_arn" \
    --resolve-conflicts OVERWRITE >/dev/null
fi

aws eks wait addon-active \
  --cluster-name "$cluster_name" \
  --region "$AWS_REGION" \
  --addon-name aws-ebs-csi-driver

printf '%s\n' "$role_arn"
