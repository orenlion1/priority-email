################################################################################
# Reconcile the CodeArtifact + slackkit-role resources into Terraform state.
#
# These resources (declared in codeartifact.tf) were created out-of-band so
# `slackkit 0.1.0` could be published and consumed before the gated apply could
# run — the scoped apply role hit a chain of permission gaps first (see the
# ci.tf history). They exist in AWS but are NOT in Terraform state, and
# CodeArtifact/IAM `Create*` are not idempotent (they error on "already
# exists"), so a plain apply would fail. These `import` blocks adopt the
# existing resources into state instead; after one successful apply Terraform
# manages them normally and these blocks can be removed.
#
# The state bucket (aws_s3_bucket.state) is deliberately NOT imported here: it
# drifted out of state separately, and aws_s3_bucket's Create is idempotent for
# an already-owned bucket in us-east-1, so the apply re-adopts it as a no-op
# once the apply role can read its config (the s3:Get* grant added in ci.tf).
#
# PREREQUISITE FOR APPLY: the DEPLOYED apply role must already carry the ci.tf
# grants (codeartifact:*, slackkit-* IAM, budgets:ListTagsForResource, the
# bucket s3:Get*) — a role cannot use a permission in the same run it grants
# itself. Those were seeded on the live roles out-of-band; this apply then makes
# them permanent. If the seed is ever lost, re-seed the apply/plan roles before
# applying.
################################################################################

# CodeArtifact resources import by ARN (the provider parses the id as one), so
# use the ARN locals from codeartifact.tf — they interpolate local.account_id,
# keeping the real id out of the committed file (the secret scan rejects it).
import {
  to = aws_codeartifact_domain.shared
  id = local.ca_domain_arn
}

import {
  to = aws_codeartifact_repository.python
  id = local.ca_repository_arn
}

import {
  to = aws_iam_role.slackkit_publish
  id = "slackkit-publish"
}

import {
  to = aws_iam_role_policy.slackkit_publish
  id = "slackkit-publish:PublishToCodeArtifact"
}

import {
  to = aws_iam_role.slackkit_reader
  id = "slackkit-reader"
}

import {
  to = aws_iam_role_policy.slackkit_reader
  id = "slackkit-reader:ReadFromCodeArtifact"
}
