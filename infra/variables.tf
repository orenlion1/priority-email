variable "aws_region" {
  type        = string
  description = "Region for all priority-email resources. The account convention is us-east-1."
  default     = "us-east-1"
}

variable "github_repository" {
  type        = string
  description = "owner/name of the repo allowed to assume the CI roles."
  default     = "orenlion1/priority-email"
}

variable "github_environment" {
  type        = string
  description = <<-EOT
    GitHub Environment pinned in the apply role's trust policy. Only a workflow
    job declaring `environment: <name>` can assume the apply role. The live
    trust policy uses "terraform-apply"; keep it unless the workflow changes.
  EOT
  default     = "terraform-apply"
}

variable "budget_notification_email" {
  type        = string
  description = "Address the monthly cost budget's forecast alarm notifies."
  default     = "orendroid@gmail.com"
}

# --- Slack management channel -------------------------------------------------
variable "manage_channel_id" {
  type        = string
  description = <<-EOT
    Slack channel ID for the priority-email management channel. The Slack events
    handler ignores messages from any other channel -- this is the trust
    boundary, not a convenience. Required before the handler is useful; set it
    to the channel where `help`, `filter …`, `provider list`, and `poll now` run.
  EOT
  default     = ""
}
