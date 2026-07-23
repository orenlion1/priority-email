################################################################################
# Shared CodeArtifact for internal Python packages (slackkit today, future
# shared libraries next), plus the two GitHub-OIDC roles that publish to and
# read from it. This is what makes `pip install slackkit` work in a Lambda build.
#
# ARCHITECTURE NOTE: shared, cross-repo publishing infra ideally lives in
# core-infra, not a single service stack. It is parked here because
# priority-email is the only stack with a working Terraform-CI-OIDC apply
# pipeline today. Everything is named `slackkit-*` / `${local.ca_domain}` so the
# eventual move to core-infra is a mechanical lift-and-shift, not a rewrite.
#
# BOOTSTRAP (why the first apply may need a re-run): the apply role grants itself
# codeartifact + `slackkit-*` IAM permissions in ci.tf. IAM is eventually
# consistent, so a role generally cannot USE a permission in the same run it
# grants ITSELF. The first apply that introduces this file can therefore fail on
# the CreateDomain / CreateRepository calls with AccessDenied. Re-run Infra Apply
# once (workflow_dispatch) — the policy change has landed and the second run
# completes cleanly. Every later apply is a single clean run.
################################################################################

locals {
  ca_domain     = "orenlion1"
  ca_repository = "python"

  ca_domain_arn     = "arn:aws:codeartifact:${local.region}:${local.account_id}:domain/${local.ca_domain}"
  ca_repository_arn = "arn:aws:codeartifact:${local.region}:${local.account_id}:repository/${local.ca_domain}/${local.ca_repository}"
  # Any pypi package in the repo (namespace is empty for pypi, hence the `//`).
  ca_package_arn = "arn:aws:codeartifact:${local.region}:${local.account_id}:package/${local.ca_domain}/${local.ca_repository}/pypi//*"

  slackkit_repo = "orenlion1/slackkit"
  # Repos allowed to READ (install) from the shared repository.
  slackkit_consumer_repos = [
    "orenlion1/re-rank",
    "orenlion1/priority-email",
  ]
}

# --- The registry ---------------------------------------------------------------

resource "aws_codeartifact_domain" "shared" {
  domain = local.ca_domain
  tags   = local.tags
}

resource "aws_codeartifact_repository" "python" {
  repository  = local.ca_repository
  domain      = aws_codeartifact_domain.shared.domain
  description = "Internal Python packages (slackkit and future shared libraries)."
  tags        = local.tags

  # No pypi upstream on purpose: this repo serves only first-party packages.
  # Consumers add it as an EXTRA index (--extra-index-url) and keep pulling
  # public dependencies straight from PyPI, so there is nothing to mirror.

  # The creates race the apply role granting itself codeartifact perms (see the
  # BOOTSTRAP note above); depends_on makes the ordering explicit even though
  # IAM propagation, not ordering, is what forces the one-time re-run.
  depends_on = [aws_iam_role_policy.terraform_apply]
}

# --- Publish role: GitHub OIDC, slackkit repo, `publish` environment only -------

data "aws_iam_policy_document" "slackkit_publish_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github_actions.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Exactly the slackkit repo, exactly its `publish` environment — the same
    # environment-pinned pattern the terraform_apply role uses, so a release can
    # publish but no other workflow (or fork) can assume this role.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.slackkit_repo}:environment:publish"]
    }
  }
}

resource "aws_iam_role" "slackkit_publish" {
  name                 = "slackkit-publish"
  description          = "GitHub OIDC role for publishing packages to CodeArtifact from the `publish` environment of ${local.slackkit_repo}."
  assume_role_policy   = data.aws_iam_policy_document.slackkit_publish_trust.json
  max_session_duration = 3600
  tags                 = local.tags
}

resource "aws_iam_role_policy" "slackkit_publish" {
  name = "PublishToCodeArtifact"
  role = aws_iam_role.slackkit_publish.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AuthToken"
        Effect   = "Allow"
        Action   = ["codeartifact:GetAuthorizationToken"]
        Resource = local.ca_domain_arn
      },
      {
        # get-authorization-token is fronted by STS; without this the CLI call
        # fails even with the codeartifact permission above.
        Sid      = "ServiceBearerToken"
        Effect   = "Allow"
        Action   = ["sts:GetServiceBearerToken"]
        Resource = "*"
        Condition = {
          StringEquals = { "sts:AWSServiceName" = "codeartifact.amazonaws.com" }
        }
      },
      {
        Sid      = "RepoEndpoint"
        Effect   = "Allow"
        Action   = ["codeartifact:GetRepositoryEndpoint", "codeartifact:ReadFromRepository"]
        Resource = local.ca_repository_arn
      },
      {
        Sid      = "Publish"
        Effect   = "Allow"
        Action   = ["codeartifact:PublishPackageVersion"]
        Resource = local.ca_package_arn
      }
    ]
  })
}

# --- Reader role: GitHub OIDC, the consuming repos, read-only -------------------

data "aws_iam_policy_document" "slackkit_reader_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github_actions.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Any run of the consuming repos may read (install). StringLike, not
    # StringEquals: their build/CI jobs are not environment-gated.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for r in local.slackkit_consumer_repos : "repo:${r}:*"]
    }
  }
}

resource "aws_iam_role" "slackkit_reader" {
  name                 = "slackkit-reader"
  description          = "GitHub OIDC role for installing internal packages from CodeArtifact in ${join(", ", local.slackkit_consumer_repos)}."
  assume_role_policy   = data.aws_iam_policy_document.slackkit_reader_trust.json
  max_session_duration = 3600
  tags                 = local.tags
}

resource "aws_iam_role_policy" "slackkit_reader" {
  name = "ReadFromCodeArtifact"
  role = aws_iam_role.slackkit_reader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AuthToken"
        Effect   = "Allow"
        Action   = ["codeartifact:GetAuthorizationToken"]
        Resource = local.ca_domain_arn
      },
      {
        Sid      = "ServiceBearerToken"
        Effect   = "Allow"
        Action   = ["sts:GetServiceBearerToken"]
        Resource = "*"
        Condition = {
          StringEquals = { "sts:AWSServiceName" = "codeartifact.amazonaws.com" }
        }
      },
      {
        Sid      = "ReadRepo"
        Effect   = "Allow"
        Action   = ["codeartifact:GetRepositoryEndpoint", "codeartifact:ReadFromRepository"]
        Resource = local.ca_repository_arn
      }
    ]
  })
}

# --- Outputs: the values to set as repo variables/secrets on the consumers ------

output "codeartifact_domain" {
  description = "Set as the CODEARTIFACT_DOMAIN repo variable on slackkit and its consumers."
  value       = aws_codeartifact_domain.shared.domain
}

output "codeartifact_repository" {
  description = "Set as the CODEARTIFACT_REPOSITORY repo variable on slackkit and its consumers."
  value       = aws_codeartifact_repository.python.repository
}

output "codeartifact_domain_owner" {
  description = "The account that owns the CodeArtifact domain (== AWS_ACCOUNT_ID)."
  value       = local.account_id
}

output "slackkit_publish_role_arn" {
  description = "Set as the AWS_PUBLISH_ROLE_ARN repo secret on slackkit (used by publish.yml)."
  value       = aws_iam_role.slackkit_publish.arn
}

output "slackkit_reader_role_arn" {
  description = "The OIDC role re-rank / priority-email assume to install from CodeArtifact."
  value       = aws_iam_role.slackkit_reader.arn
}
