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
