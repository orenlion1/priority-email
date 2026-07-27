# GitHub Actions OIDC roles for this repo's Terraform workflows. Recovered from
# the live state (the source was never committed) and extended so the apply role
# can also manage the new Slack events Lambda and its secret containers.
#
# priority-email governs its OWN CI roles rather than using core-infra's shared
# ci-terraform-apply stack: it is self-contained apart from the shared tf-state
# bucket. Role ARNs are published as repo VARIABLES (outputs.tf), not secrets.
#
# The trust policies use the plain `repo:owner/name:...` subject form, matching
# what is live. Do not "upgrade" to the numeric-ID form without a plan: it would
# rewrite the trust policy.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# --- Plan role: read-only, assumable by any run on this repo -------------------
data "aws_iam_policy_document" "trust_any_run" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
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
  name               = "priority-email-terraform-plan"
  description        = "Read-only role for `terraform plan` on ${var.github_repository}. Assumable by any run; cannot mutate anything."
  assume_role_policy = data.aws_iam_policy_document.trust_any_run.json
}

data "aws_iam_policy_document" "terraform_plan" {
  statement {
    sid    = "DescribeStack"
    effect = "Allow"
    actions = [
      "lambda:Get*", "lambda:List*",
      "scheduler:GetSchedule", "scheduler:ListSchedules", "scheduler:ListTagsForResource",
      "logs:DescribeLogGroups", "logs:ListTagsForResource",
      "budgets:ViewBudget", "budgets:DescribeBudget", "budgets:ListTagsForResource",
      "s3:GetBucket*", "s3:GetEncryptionConfiguration",
      "secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy", "secretsmanager:ListSecretVersionIds",
      "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListRoleTags",
      "iam:GetOpenIDConnectProvider", "sts:GetCallerIdentity",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "StateBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::ensemble-grafana-tf-state-${data.aws_caller_identity.current.account_id}"]
  }

  statement {
    sid       = "StateObjectRead"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::ensemble-grafana-tf-state-${data.aws_caller_identity.current.account_id}/stacks/priority-email/terraform.tfstate"]
  }

  statement {
    sid       = "StateLockFile"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::ensemble-grafana-tf-state-${data.aws_caller_identity.current.account_id}/stacks/priority-email/terraform.tfstate.tflock"]
  }
}

resource "aws_iam_role_policy" "terraform_plan" {
  name   = "TerraformPlanReadOnly"
  role   = aws_iam_role.terraform_plan.id
  policy = data.aws_iam_policy_document.terraform_plan.json
}

# --- Apply role: scoped to the deploy environment -----------------------------
data "aws_iam_policy_document" "trust_guarded_environment" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "terraform_apply" {
  name               = "priority-email-terraform-apply"
  description        = "Read+write role for `terraform apply` on ${var.github_repository}. Only assumable from the required-reviewer \"${var.github_environment}\" GitHub environment."
  assume_role_policy = data.aws_iam_policy_document.trust_guarded_environment.json
}

locals {
  acct   = data.aws_caller_identity.current.account_id
  region = data.aws_region.current.name
}

data "aws_iam_policy_document" "terraform_apply" {
  statement {
    sid    = "DescribeStack"
    effect = "Allow"
    actions = [
      "lambda:Get*", "lambda:List*",
      "scheduler:GetSchedule", "scheduler:ListSchedules", "scheduler:ListTagsForResource",
      "logs:DescribeLogGroups",
      "budgets:ViewBudget", "budgets:DescribeBudget", "budgets:ListTagsForResource",
      "secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy", "secretsmanager:ListSecretVersionIds",
      "iam:GetOpenIDConnectProvider", "sts:GetCallerIdentity",
    ]
    resources = ["*"]
  }

  # Both Lambdas (poller and slack-events) and their Function URL config. Broadened
  # from the poller-only original to the priority-email-* prefix so the same role
  # manages the new handler.
  statement {
    sid     = "ManageFunctions"
    effect  = "Allow"
    actions = ["lambda:*"]
    resources = [
      "arn:aws:lambda:${local.region}:${local.acct}:function:priority-email-*",
      "arn:aws:lambda:${local.region}:${local.acct}:function:priority-email-*:*",
    ]
  }

  statement {
    sid       = "ManageSchedule"
    effect    = "Allow"
    actions   = ["scheduler:CreateSchedule", "scheduler:UpdateSchedule", "scheduler:DeleteSchedule", "scheduler:TagResource", "scheduler:UntagResource"]
    resources = ["arn:aws:scheduler:${local.region}:${local.acct}:schedule/default/priority-email-poller"]
  }

  statement {
    sid       = "ManageLogGroups"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource", "logs:ListTagsForResource"]
    resources = ["arn:aws:logs:${local.region}:${local.acct}:log-group:/aws/lambda/priority-email-*"]
  }

  statement {
    sid       = "ManageBudget"
    effect    = "Allow"
    actions   = ["budgets:ModifyBudget", "budgets:CreateBudget", "budgets:DeleteBudget"]
    resources = ["arn:aws:budgets::${local.acct}:budget/priority-email-monthly"]
  }

  statement {
    sid    = "ManageOwnRoles"
    effect = "Allow"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole", "iam:PassRole",
      "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies", "iam:ListRoleTags", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
      "iam:UpdateAssumeRolePolicy",
    ]
    resources = ["arn:aws:iam::${local.acct}:role/priority-email-*"]
  }

  # New: manage the Slack secret CONTAINERS (never their values). No
  # GetSecretValue anywhere on the apply role, so a leaked CI token cannot read
  # the signing secret or bot token -- only create/rename/tag the containers.
  statement {
    sid    = "ManageSlackSecretContainers"
    effect = "Allow"
    actions = [
      "secretsmanager:CreateSecret", "secretsmanager:DeleteSecret",
      "secretsmanager:UpdateSecret", "secretsmanager:TagResource", "secretsmanager:UntagResource",
    ]
    resources = ["arn:aws:secretsmanager:${local.region}:${local.acct}:secret:priority-email/slack-*"]
  }

  statement {
    sid       = "ManageAppStateBucket"
    effect    = "Allow"
    actions   = ["s3:CreateBucket", "s3:GetBucket*", "s3:PutBucket*", "s3:GetEncryptionConfiguration", "s3:PutEncryptionConfiguration", "s3:ListBucket"]
    resources = ["arn:aws:s3:::priority-email-state-${local.acct}"]
  }

  # The apply role can create/version the state bucket but must never read or
  # write the filter values and checkpoints inside it.
  statement {
    sid       = "NoAppStateContentsFromCI"
    effect    = "Deny"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::priority-email-state-${local.acct}/*"]
  }

  # And never the runtime secret's value.
  statement {
    sid       = "NoRuntimeSecretFromCI"
    effect    = "Deny"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.runtime_secret_arn_wildcard]
  }

  statement {
    sid       = "StateBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::ensemble-grafana-tf-state-${local.acct}"]
  }

  statement {
    sid       = "StateObjectReadWrite"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::ensemble-grafana-tf-state-${local.acct}/stacks/priority-email/terraform.tfstate"]
  }

  statement {
    sid       = "StateLockFile"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::ensemble-grafana-tf-state-${local.acct}/stacks/priority-email/terraform.tfstate.tflock"]
  }
}

resource "aws_iam_role_policy" "terraform_apply" {
  name   = "TerraformApplyScoped"
  role   = aws_iam_role.terraform_apply.id
  policy = data.aws_iam_policy_document.terraform_apply.json
}
