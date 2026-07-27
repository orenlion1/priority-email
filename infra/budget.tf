# A forecast alarm, not a hard cap: the whole point of the EKS->Lambda migration
# was cost, so a projected month over $5 should page a human. AWS cannot stop
# spend, only warn, so this notifies at a forecast breach rather than pretending
# to enforce a ceiling.

resource "aws_budgets_budget" "monthly" {
  name         = "priority-email-monthly"
  budget_type  = "COST"
  limit_amount = "5.0"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "FORECASTED"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.budget_notification_email]
  }
}
