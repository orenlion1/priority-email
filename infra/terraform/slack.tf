# --- Slack events handler: the management channel command bot ---
#
# scripts/slack/commands.py (the parser) and scripts/slack/slack_handler.py (the
# handler) run behind a public Lambda Function URL. This is the endpoint the
# parser never had: slackkit verifies the Slack signature, then routes
# help / filter / provider / poll. A `filter add|remove` writes the S3 filter
# files the poller reads and appends an age-encrypted op (public key only).
#
# Deliberately a SEPARATE function from the poller: this one is public and
# latency-bound (Slack retries after 3s), the poller is private and runs for
# minutes. One function would hand a public endpoint the poller's runtime-secret
# access. Their only link is `poll now`, which invokes the poller.

locals {
  slack_name = "priority-email-slack-events"

  slack_signing_secret_arn = aws_secretsmanager_secret.slack_signing_secret.arn
  slack_bot_token_arn      = aws_secretsmanager_secret.slack_bot_token.arn
}

# --- Secret containers (values set out-of-band; never in Terraform state) ---
resource "aws_secretsmanager_secret" "slack_signing_secret" {
  name        = "priority-email/slack-signing-secret"
  description = "Slack signing secret, verified on every request to the events Function URL."
  tags        = local.tags
}

resource "aws_secretsmanager_secret" "slack_bot_token" {
  name        = "priority-email/slack-bot-token"
  description = "Slack bot token the events handler uses to reply in the management channel."
  tags        = local.tags
}

# --- Execution role ---
resource "aws_iam_role" "slack" {
  name               = local.slack_name
  assume_role_policy = data.aws_iam_policy_document.assume.json # lambda.amazonaws.com, from main.tf
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "slack_basic" {
  role       = aws_iam_role.slack.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "slack" {
  name = "priority-email-slack-events"
  role = aws_iam_role.slack.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read the filter files and checkpoint, write the filter files, append
        # encrypted ops. Object-level only.
        Sid      = "FilterStore"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.state.arn}/*"
      },
      {
        # Verify inbound requests and reply. Deliberately NOT the runtime secret:
        # a public endpoint must not read the poller's OAuth tokens and keys.
        Sid      = "SlackSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [local.slack_signing_secret_arn, local.slack_bot_token_arn]
      },
      {
        # `poll now` runs the poller immediately -- that one function, nothing else.
        Sid      = "InvokePoller"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.poller.arn
      }
    ]
  })
}

# --- Function ---
resource "aws_cloudwatch_log_group" "slack" {
  name              = "/aws/lambda/${local.slack_name}"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_lambda_function" "slack" {
  function_name    = local.slack_name
  role             = aws_iam_role.slack.arn
  runtime          = "python3.13"
  handler          = "scripts.slack.slack_handler.handler"
  filename         = var.slack_lambda_zip
  source_code_hash = filebase64sha256(var.slack_lambda_zip)

  # Slack retries a response slower than 3s; 10s covers a cold start plus one
  # reply without inviting a retry storm.
  timeout     = var.slack_lambda_timeout_seconds
  memory_size = var.slack_lambda_memory_mb

  environment {
    variables = {
      STATE_BUCKET             = aws_s3_bucket.state.id
      SLACK_SIGNING_SECRET_ARN = local.slack_signing_secret_arn
      SLACK_BOT_TOKEN_ARN      = local.slack_bot_token_arn
      RUNTIME_SECRET_ID        = var.runtime_secret_id
      MANAGE_CHANNEL_ID        = var.manage_channel_id
      POLLER_FUNCTION_NAME     = aws_lambda_function.poller.function_name
      # `age` binary and committed public key, both bundled at the zip root by
      # scripts/aws/build-slack-lambda-zip.sh, so an op is encrypted with the
      # public key without the private key ever reaching this public function.
      AGE_BIN             = "/var/task/age"
      AGE_RECIPIENTS_PATH = "/var/task/filters/age-recipients.pub"
    }
  }

  depends_on = [aws_cloudwatch_log_group.slack]
  tags       = local.tags

  # CODE is deployed by scripts/aws/deploy-slack-lambda.sh, not Terraform.
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

# --- Public Function URL ---
# Slack cannot present AWS credentials; the security boundary is slackkit's
# signature check, which runs first and fails closed. AWS_IAM here would make
# the endpoint unreachable by the only caller it exists for.
resource "aws_lambda_function_url" "slack" {
  function_name      = aws_lambda_function.slack.function_name
  authorization_type = "NONE"
}

# authorization_type = NONE is not enough on its own: the function needs a
# resource policy allowing lambda:InvokeFunctionUrl, or every request 403s.
resource "aws_lambda_permission" "slack_url" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.slack.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# BOTH actions are required: since October 2025 Lambda also checks
# lambda:InvokeFunction for Function URL calls, and a grant that worked before
# now 403s with no hint the second action is missing. No function_url_auth_type
# here -- Lambda rejects that condition on this action.
resource "aws_lambda_permission" "slack_invoke" {
  statement_id  = "AllowPublicFunctionUrlInvokeFunction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack.function_name
  principal     = "*"
}

output "slack_events_url" {
  description = "Paste into the Slack app's Event Subscriptions Request URL, then subscribe to message.channels for the management channel."
  value       = aws_lambda_function_url.slack.function_url
}
