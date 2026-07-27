output "function_name" {
  value       = aws_lambda_function.poller.function_name
  description = "Poller Lambda. Invoke manually with: aws lambda invoke --function-name priority-email-poller /dev/stdout"
}

output "schedule" {
  value       = aws_scheduler_schedule.poll.schedule_expression
  description = "How often the poller runs."
}

output "state_bucket" {
  value       = aws_s3_bucket.state.bucket
  description = "S3 bucket holding poller state, assembled filters, and the encrypted filter ops log."
}

output "slack_events_url" {
  value       = aws_lambda_function_url.slack_events.function_url
  description = "Paste into the Slack app's Event Subscriptions Request URL, then subscribe to message.channels for the management channel."
}

output "terraform_plan_role_arn" {
  value       = aws_iam_role.terraform_plan.arn
  description = "Publish as the AWS_PLAN_ROLE_ARN repo variable. Not a secret."
}

output "terraform_apply_role_arn" {
  value       = aws_iam_role.terraform_apply.arn
  description = "Publish as the AWS_APPLY_ROLE_ARN repo variable. Not a secret."
}
