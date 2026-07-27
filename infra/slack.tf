# Slack events handler: the missing half of the command bot. The parser
# (scripts/slack/commands.py) and handler (scripts/slack/slack_handler.py) were
# written against slackkit but had no endpoint; this is the public Function URL
# and the Lambda behind it, mirroring re-rank's re-rank-slack-events.
#
# Separate function from the poller, deliberately. This one is public and
# latency-bound (Slack retries after 3s); the poller is private and runs for
# minutes. One function would give a public endpoint the poller's runtime-secret
# access. Their only coupling is `poll now`, which invokes the poller.

resource "aws_iam_role" "slack_events" {
  name               = "priority-email-slack-events"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "slack_events_basic" {
  role       = aws_iam_role.slack_events.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "slack_events" {
  # The filter store: read the filter files and the checkpoint, write the filter
  # files and append encrypted ops. Object-level only -- the handler never needs
  # to manage the bucket itself.
  statement {
    sid       = "FilterStore"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }

  # Verify inbound requests (signing secret) and reply (bot token). Deliberately
  # NOT the runtime secret: a public endpoint must not be able to read the
  # poller's OAuth tokens and provider keys.
  statement {
    sid     = "SlackSecrets"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.slack_signing_secret.arn,
      aws_secretsmanager_secret.slack_bot_token.arn,
    ]
  }

  # `poll now` runs the poller immediately. Scoped to that one function -- the
  # handler can start it and nothing else.
  statement {
    sid       = "InvokePoller"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.poller.arn]
  }
}

resource "aws_iam_role_policy" "slack_events" {
  name   = "priority-email-slack-events"
  role   = aws_iam_role.slack_events.id
  policy = data.aws_iam_policy_document.slack_events.json
}

resource "aws_lambda_function" "slack_events" {
  function_name = "priority-email-slack-events"
  role          = aws_iam_role.slack_events.arn
  runtime       = "python3.13"
  handler       = "scripts.slack.slack_handler.handler"
  architectures = ["x86_64"]

  # Slack retries a response slower than 3s; 10s leaves headroom for a cold
  # start plus one Slack API reply without inviting a retry storm.
  timeout     = 10
  memory_size = 256

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      STATE_BUCKET             = aws_s3_bucket.state.bucket
      SLACK_SIGNING_SECRET_ARN = aws_secretsmanager_secret.slack_signing_secret.arn
      SLACK_BOT_TOKEN_ARN      = aws_secretsmanager_secret.slack_bot_token.arn
      RUNTIME_SECRET_ID        = local.runtime_secret_name
      MANAGE_CHANNEL_ID        = var.manage_channel_id
      POLLER_FUNCTION_NAME     = aws_lambda_function.poller.function_name
      # The `age` binary and the committed public key, both bundled at the zip
      # root by scripts/aws/build-slack-lambda-zip.sh, so the handler can append
      # an encrypted filter op without the private key.
      AGE_BIN             = "/var/task/age"
      AGE_RECIPIENTS_PATH = "/var/task/filters/age-recipients.pub"
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

# Public endpoint. Slack cannot present AWS credentials, so authentication is the
# signing-secret check inside slackkit, which runs before anything else and fails
# closed. AWS_IAM auth here would make the endpoint unreachable by Slack.
resource "aws_lambda_function_url" "slack_events" {
  function_name      = aws_lambda_function.slack_events.function_name
  authorization_type = "NONE"
}

# authorization_type = NONE is not sufficient alone -- the function needs a
# resource policy allowing lambda:InvokeFunctionUrl, or every request 403s.
resource "aws_lambda_permission" "slack_events_url" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.slack_events.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# BOTH actions are required: since October 2025 Lambda also checks
# lambda:InvokeFunction for Function URL calls, and grants that worked before
# now 403 with no hint that a second action is missing. No function_url_auth_type
# here -- Lambda rejects that condition on this action.
resource "aws_lambda_permission" "slack_events_invoke" {
  statement_id  = "AllowPublicFunctionUrlInvokeFunction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_events.function_name
  principal     = "*"
}

resource "aws_cloudwatch_log_group" "slack_events" {
  name              = "/aws/lambda/${aws_lambda_function.slack_events.function_name}"
  retention_in_days = 14
}
