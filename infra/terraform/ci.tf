################################################################################
# GitHub Actions -> AWS, via OIDC. No AWS access keys exist anywhere.
#
# Two roles, following the orenlion1 standard (see core-infra
# docs/standards/terraform-ci-oidc.md), first proven in winnow:
#
#   terraform_plan   read-only, assumable by ANY run of this repo. Safe on PRs
#                    because it cannot mutate anything.
#   terraform_apply  read+write, assumable ONLY from the required-reviewer
#                    "terraform-apply" GitHub environment. A run cannot change
#                    infrastructure without a human clicking approve — and
#                    deleting `environment:` from the workflow does not help:
#                    the trust policy pins the OIDC subject to that exact
#                    environment, so the role simply won't mint credentials.
#
# The role ARNs are not secrets: the trust policy pins the OIDC subject to this
# repo, so a fork cannot assume them. They are published as repo variables
# (AWS_PLAN_ROLE_ARN / AWS_APPLY_ROLE_ARN) and the workflow skips until set.
################################################################################

# AWS permits exactly ONE OIDC provider per issuer per account; ensemble-retail
# created it. Its ARN is deterministic from the account id, so construct it
# rather than reading it via a data source: the aws_iam_openid_connect_provider
# data source calls iam:ListOpenIDConnectProviders, which the scoped plan/apply
# roles are (deliberately) not granted, and which no trust policy actually needs
# — only the ARN string is used below.
locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  github_oidc_provider_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"

  # Shared Terraform state bucket (owned by core-infra's stacks/ci-terraform-apply).
  # CI may touch ONLY priority-email's own state object and its S3-native lock file.
  tf_state_bucket     = "ensemble-grafana-tf-state-${local.account_id}"
  tf_state_bucket_arn = "arn:aws:s3:::${local.tf_state_bucket}"
  tf_state_obj_arn    = "arn:aws:s3:::${local.tf_state_bucket}/stacks/priority-email/terraform.tfstate"
  tf_lock_obj_arn     = "arn:aws:s3:::${local.tf_state_bucket}/stacks/priority-email/terraform.tfstate.tflock"

  # Resources this stack manages — the apply role is scoped to exactly these.
  app_state_bucket_arn = "arn:aws:s3:::priority-email-state-${local.account_id}"
  lambda_arn           = "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.name}"
  schedule_arn         = "arn:aws:scheduler:${local.region}:${local.account_id}:schedule/default/${local.name}"
  log_group_arn        = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.name}*"
  budget_arn           = "arn:aws:budgets::${local.account_id}:budget/priority-email-monthly"

  # IAM roles this stack's apply role may manage: its own (priority-email-*). No
  # wildcard on all roles — the prefix is a namespace this stack actually owns.
  managed_role_arns = [
    "arn:aws:iam::${local.account_id}:role/priority-email-*",
  ]
}

# ---- plan: read-only, any run on this repo ----

data "aws_iam_policy_document" "trust_any_run" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:*"]
    }
  }
}

resource "aws_iam_role" "terraform_plan" {
  name                 = "priority-email-terraform-plan"
  description          = "Read-only role for `terraform plan` on ${var.github_repository}. Assumable by any run; cannot mutate anything."
  assume_role_policy   = data.aws_iam_policy_document.trust_any_run.json
  max_session_duration = 3600
  tags                 = local.tags
}

resource "aws_iam_role_policy" "terraform_plan" {
  # checkov:skip=CKV_AWS_355:List/Describe APIs IAM only evaluates against '*'; every action here is read-only, which is the point of splitting plan from apply.
  # checkov:skip=CKV_AWS_287:iam:Get*/List* return role metadata (trust/policy names), never credentials. Terraform must refresh the roles it manages or report spurious drift.
  name = "TerraformPlanReadOnly"
  role = aws_iam_role.terraform_plan.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DescribeStack"
        Effect = "Allow"
        Action = [
          "lambda:Get*",
          "lambda:List*",
          "scheduler:GetSchedule",
          "scheduler:ListSchedules",
          "scheduler:ListTagsForResource",
          "logs:DescribeLogGroups",
          "logs:ListTagsForResource",
          "budgets:ViewBudget",
          "budgets:DescribeBudget",
          "budgets:ListTagsForResource",
          "s3:GetBucket*",
          "s3:GetEncryptionConfiguration",
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:ListRoleTags",
          "iam:GetOpenIDConnectProvider",
          "sts:GetCallerIdentity"
        ]
        Resource = "*"
      },
      {
        Sid      = "StateBucketList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = local.tf_state_bucket_arn
      },
      {
        Sid      = "StateObjectRead"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = local.tf_state_obj_arn
      },
      {
        # plan takes and releases the S3-native lock too, not just apply
        Sid      = "StateLockFile"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = local.tf_lock_obj_arn
      }
    ]
  })
}

# ---- apply: read+write, only from the guarded environment ----

data "aws_iam_policy_document" "trust_guarded_environment" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # StringEquals, not StringLike: exactly this repo in exactly this environment.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "terraform_apply" {
  name                 = "priority-email-terraform-apply"
  description          = "Read+write role for `terraform apply` on ${var.github_repository}. Only assumable from the required-reviewer \"${var.github_environment}\" GitHub environment."
  assume_role_policy   = data.aws_iam_policy_document.trust_guarded_environment.json
  max_session_duration = 3600
  tags                 = local.tags
}

resource "aws_iam_role_policy" "terraform_apply" {
  # checkov:skip=CKV_AWS_355:List/Describe APIs IAM only evaluates against '*'.
  # checkov:skip=CKV_AWS_287:iam:Get*/List* return role metadata, never credentials.
  name = "TerraformApplyScoped"
  role = aws_iam_role.terraform_apply.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Refresh/describe across the stack (evaluated against '*' by these APIs).
        Sid    = "DescribeStack"
        Effect = "Allow"
        Action = [
          "lambda:Get*",
          "lambda:List*",
          "scheduler:GetSchedule",
          "scheduler:ListSchedules",
          "scheduler:ListTagsForResource",
          "logs:DescribeLogGroups",
          "budgets:ViewBudget",
          "budgets:DescribeBudget",
          "budgets:ListTagsForResource",
          "iam:GetOpenIDConnectProvider",
          "sts:GetCallerIdentity"
        ]
        Resource = "*"
      },
      {
        Sid      = "ManageFunction"
        Effect   = "Allow"
        Action   = ["lambda:*"]
        Resource = ["${local.lambda_arn}", "${local.lambda_arn}:*"]
      },
      {
        Sid    = "ManageSchedule"
        Effect = "Allow"
        Action = [
          "scheduler:CreateSchedule",
          "scheduler:UpdateSchedule",
          "scheduler:DeleteSchedule",
          "scheduler:TagResource",
          "scheduler:UntagResource"
        ]
        Resource = local.schedule_arn
      },
      {
        Sid    = "ManageLogGroup"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy",
          "logs:TagResource",
          "logs:UntagResource",
          "logs:ListTagsForResource"
        ]
        Resource = local.log_group_arn
      },
      {
        Sid    = "ManageBudget"
        Effect = "Allow"
        Action = [
          "budgets:ModifyBudget",
          "budgets:CreateBudget",
          "budgets:DeleteBudget"
        ]
        Resource = local.budget_arn
      },
      {
        # IAM for the roles this stack owns only (lambda, scheduler, and these two
        # CI roles — all named priority-email-*). No wildcard on all roles.
        Sid    = "ManageOwnRoles"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:PassRole",
          "iam:PutRolePolicy",
          "iam:GetRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:ListRoleTags",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:UpdateAssumeRolePolicy"
        ]
        Resource = local.managed_role_arns
      },
      {
        # Bucket-level management of the app's own state/filters bucket. No
        # DeleteBucket (it holds the durable poller checkpoint) and no object
        # access — see the deny below.
        Sid    = "ManageAppStateBucket"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:GetBucket*",
          "s3:PutBucket*",
          "s3:GetEncryptionConfiguration",
          "s3:PutEncryptionConfiguration",
          "s3:ListBucket"
        ]
        Resource = local.app_state_bucket_arn
      },
      {
        # CI builds the app state/filters bucket; it has no business reading the
        # poller's runtime checkpoint or the decrypted filters inside it.
        Sid      = "NoAppStateContentsFromCI"
        Effect   = "Deny"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${local.app_state_bucket_arn}/*"
      },
      {
        # The runtime secret is runtime-only. CI provisions the role that reads
        # it but must never read it itself.
        Sid      = "NoRuntimeSecretFromCI"
        Effect   = "Deny"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = local.runtime_secret_arn
      },
      {
        Sid      = "StateBucketList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = local.tf_state_bucket_arn
      },
      {
        Sid      = "StateObjectReadWrite"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = local.tf_state_obj_arn
      },
      {
        Sid      = "StateLockFile"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = local.tf_lock_obj_arn
      }
    ]
  })
}

output "terraform_plan_role_arn" {
  description = "Set as the AWS_PLAN_ROLE_ARN repo variable."
  value       = aws_iam_role.terraform_plan.arn
}

output "terraform_apply_role_arn" {
  description = "Set as the AWS_APPLY_ROLE_ARN repo variable."
  value       = aws_iam_role.terraform_apply.arn
}
