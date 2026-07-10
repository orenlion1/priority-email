output "function_name" {
  value = aws_lambda_function.poller.function_name
}

output "state_bucket" {
  value = aws_s3_bucket.state.id
}

output "schedule" {
  value = aws_scheduler_schedule.poll.schedule_expression
}
