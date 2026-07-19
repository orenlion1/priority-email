terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Reuses the shared state bucket that core-infra's stacks/ci-terraform-apply
  # owns (ensemble-grafana-tf-state-<account_id>). priority-email is just a new
  # key in that bucket, not a new bucket — one bootstrap per account is enough.
  # bucket/region and the use_lockfile flag come from -backend-config at init
  # (see CLAUDE.md "Operator-only surface"). State locking is S3-native
  # (use_lockfile), matching core-infra — there is no DynamoDB lock table.
  backend "s3" {
    key     = "stacks/priority-email/terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
}
