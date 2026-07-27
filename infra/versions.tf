terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Partial backend: only key and encrypt are committed. bucket, region and
  # use_lockfile are supplied via -backend-config so the state location is not
  # baked into the repo. Locking is S3-native (a .tflock object beside the state
  # file); there is no DynamoDB lock table (the account's shared lock table was
  # destroyed and must not be reintroduced).
  backend "s3" {
    key     = "stacks/priority-email/terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  # These two tags are on every resource in the live state; setting them as
  # default_tags reproduces that exactly. "serverless" is the stack label the
  # out-of-band migration applied, kept as-is so the first plan shows no tag
  # churn -- do not rename it without a plan that confirms no drift.
  default_tags {
    tags = {
      Application = "priority-email"
      Stack       = "serverless"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
