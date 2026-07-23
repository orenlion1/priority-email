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

  # IAM roles this stack's apply role may manage: its own (priority-email-*) plus
  # the shared publishing roles in codeartifact.tf (slackkit-*). No wildcard on
  # all roles — each prefix is a namespace this stack actually owns.
  managed_role_arns = [
    "arn:aws:iam::${local.account_id}:role/priority-email-*",
    "arn:aws:iam::${local.account_id}:role/slackkit-*",
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
          "codeartifact:DescribeDomain",
          "codeartifact:DescribeRepository",
          "codeartifact:ListRepositoriesInDomain",
          "codeartifact:ListTagsForResource",
          "codeartifact:GetDomainPermissionsPolicy",
          "codeartifact:GetRepositoryPermissionsPolicy",
          "codeartifact:GetRepositoryEndpoint",
          "s3:GetBucket*",
          "s3:GetEncryptionConfiguration",
          # The aws_s3_bucket read reads these sub-configs too; they are not
          # covered by s3:GetBucket* (differently named IAM actions). Needed once
          # the state bucket is back in state and refreshed each plan.
          "s3:GetAccelerateConfiguration",
          "s3:GetLifecycleConfiguration",
          "s3:GetReplicationConfiguration",
          "s3:GetAnalyticsConfiguration",
          "s3:GetMetricsConfiguration",
          "s3:GetInventoryConfiguration",
          "s3:GetIntelligentTieringConfiguration",
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
          "codeartifact:DescribeDomain",
          "codeartifact:DescribeRepository",
          "codeartifact:ListRepositoriesInDomain",
          "codeartifact:ListTagsForResource",
          "codeartifact:GetDomainPermissionsPolicy",
          "codeartifact:GetRepositoryPermissionsPolicy",
          "codeartifact:GetRepositoryEndpoint",
          "iam:GetOpenIDConnectProvider",
          "sts:GetCallerIdentity"
        ]
        Resource = "*"
      },
      {
        # Create/manage the shared CodeArtifact domain + repository (codeartifact.tf),
        # scoped to exactly those two resources. Read/describe is granted broadly
        # above; only the mutating calls are pinned here.
        Sid    = "ManageCodeArtifact"
        Effect = "Allow"
        Action = [
          "codeartifact:CreateDomain",
          "codeartifact:DeleteDomain",
          "codeartifact:PutDomainPermissionsPolicy",
          "codeartifact:DeleteDomainPermissionsPolicy",
          "codeartifact:CreateRepository",
          "codeartifact:UpdateRepository",
          "codeartifact:DeleteRepository",
          "codeartifact:PutRepositoryPermissionsPolicy",
          "codeartifact:DeleteRepositoryPermissionsPolicy",
          "codeartifact:TagResource",
          "codeartifact:UntagResource"
        ]
        Resource = [local.ca_domain_arn, local.ca_repository_arn]
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
        # s3:Get* is bucket-scoped here (the resource is the bucket, not its
        # objects), so it grants every bucket-config read the aws_s3_bucket
        # refresh performs — accelerate, lifecycle, replication, etc., which
        # s3:GetBucket* does not cover — while the NoAppStateContentsFromCI deny
        # below still blocks all object access.
        Action = [
          "s3:CreateBucket",
          "s3:Get*",
          "s3:PutBucket*",
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
