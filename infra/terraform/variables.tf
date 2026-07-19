variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "lambda_zip" {
  type        = string
  description = "Path to the built Lambda deployment zip (scripts/aws/build-lambda-zip.sh)."
  default     = "../../dist/priority-email-lambda.zip"
}

variable "runtime_secret_id" {
  type        = string
  description = "Secrets Manager secret whose value is the poller's .env (OAuth tokens, Slack, push)."
  default     = "priority-email/runtime"
}

variable "poll_rate" {
  type        = string
  description = "EventBridge Scheduler rate for one poll cycle."
  default     = "rate(5 minutes)"
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 300
}

variable "lambda_memory_mb" {
  type    = number
  default = 512
}

variable "budget_notification_email" {
  type    = string
  default = "orendroid@gmail.com"
}

variable "monthly_budget_usd" {
  type    = number
  default = 5
}

# ---- CI (GitHub Actions -> AWS via OIDC; see ci.tf) ----

variable "github_repository" {
  type        = string
  description = "owner/name. Pins the OIDC trust policies in ci.tf to this repo."
  default     = "orenlion1/priority-email"
}

variable "github_environment" {
  type        = string
  description = <<-EOT
    GitHub environment that gates `terraform apply`. Configure it with required
    reviewers in repo settings: the apply role cannot be assumed from anywhere
    else, so no CI run can mutate infrastructure without a human approving first.
  EOT
  default     = "terraform-apply"
}
