# The scheduled poller: EventBridge invokes this Lambda every few minutes and
# each invocation runs exactly one poll cycle (scripts/aws/lambda_function.py ->
# scripts/poll-email.py). It replaced the EKS run-poller-loop.sh pod after the
# cost-reduction migration; durable state and filters live in the S3 bucket
# below instead of a PVC/ConfigMap.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "priority-email-poller-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# The poller reads the runtime secret (its value is the .env verbatim) and reads
# and writes the state bucket (checkpoint JSON and the assembled filter files).
# No Slack signing secret: the poller never verifies an inbound request.
# The runtime secret (its value is the .env verbatim) is created out-of-band by
# scripts/aws/sync-runtime-secret.sh, not by this stack -- so it is referenced by
# its literal ARN, never managed here. The `-*` suffix matches the random tail
# Secrets Manager appends, exactly as the live policy has it.
locals {
  runtime_secret_name = "priority-email/runtime"
  runtime_secret_arn_wildcard = format(
    "arn:aws:secretsmanager:%s:%s:secret:%s-*",
    data.aws_region.current.name,
    data.aws_caller_identity.current.account_id,
    local.runtime_secret_name,
  )
}

data "aws_iam_policy_document" "poller" {
  statement {
    sid       = "RuntimeSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.runtime_secret_arn_wildcard]
  }

  statement {
    sid       = "StateAndFilters"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "priority-email-runtime"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.poller.json
}

# CI (scripts/aws/deploy-lambda.sh) owns the code, so the function ships with a
# placeholder and ignore_changes keeps Terraform from fighting the deploy
# pipeline over the zip.
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/.build/placeholder.zip"

  source {
    filename = "index.py"
    content  = "# Replaced by scripts/aws/deploy-lambda.sh. See .github/workflows/.\n"
  }
}

resource "aws_lambda_function" "poller" {
  function_name = "priority-email-poller"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.13"
  handler       = "scripts.aws.lambda_function.handler"
  architectures = ["x86_64"]

  # One cycle is a handful of provider calls; 300s is comfortably more than a
  # cycle needs and well under the 15-minute ceiling.
  timeout     = 300
  memory_size = 512

  # One at a time: overlapping cycles would double-poll and race on the shared
  # S3 checkpoint. The 5-minute schedule never needs more than one runner.
  reserved_concurrent_executions = 1

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      RUNTIME_SECRET_ID = local.runtime_secret_name
      STATE_BUCKET      = aws_s3_bucket.state.bucket
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_cloudwatch_log_group" "poller" {
  name              = "/aws/lambda/${aws_lambda_function.poller.function_name}"
  retention_in_days = 14
}

# --- Schedule -----------------------------------------------------------------
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "priority-email-poller-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.poller.arn,
      "${aws_lambda_function.poller.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke-poller"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "poll" {
  name       = "priority-email-poller"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "rate(5 minutes)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.poller.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      # No retries: a missed cycle is picked up by the next one five minutes
      # later, and a retry would just double-poll.
      maximum_retry_attempts       = 0
      maximum_event_age_in_seconds = 86400
    }
  }
}
