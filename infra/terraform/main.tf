data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  name = "priority-email-poller"
  tags = {
    Application = "priority-email"
    Stack       = "serverless"
  }
  runtime_secret_arn = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.runtime_secret_id}-*"
}

# --- State + filters bucket (replaces the k8s PVC + filters ConfigMap) ---
resource "aws_s3_bucket" "state" {
  bucket = "priority-email-state-${data.aws_caller_identity.current.account_id}"
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# --- Lambda execution role (least privilege) ---
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "RuntimeSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.runtime_secret_arn]
  }
  statement {
    sid       = "StateAndFilters"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "priority-email-runtime"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# --- Function (Python 3.13, one poll cycle per invocation) ---
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_lambda_function" "poller" {
  function_name    = local.name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = "scripts.aws.lambda_function.handler"
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb

  # State is a single S3 object (read-modify-write); serialize invocations so two
  # poll cycles never race on the checkpoint.
  reserved_concurrent_executions = 1

  environment {
    variables = {
      STATE_BUCKET      = aws_s3_bucket.state.id
      RUNTIME_SECRET_ID = var.runtime_secret_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
  tags       = local.tags
}

# --- EventBridge Scheduler: one poll cycle every interval (replaces the pod loop) ---
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-poller"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [aws_lambda_function.poller.arn, "${aws_lambda_function.poller.arn}:*"]
    }]
  })
}

resource "aws_scheduler_schedule" "poll" {
  name = local.name

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.poll_rate
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.poller.arn
    role_arn = aws_iam_role.scheduler.arn
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

# --- Cost guardrail ---
resource "aws_budgets_budget" "monthly" {
  name         = "priority-email-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_notification_email]
  }
}
