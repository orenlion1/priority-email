# The poller's durable store: provider checkpoints (state/…json), the assembled
# sender filters (filters/<kind>-filters.txt), and the encrypted filter ops log
# the Slack handler appends to (filters/ops/…age). Versioned so a bad filter
# assembly or a fat-fingered Slack edit can be rolled back.

resource "aws_s3_bucket" "state" {
  bucket = "priority-email-state-${data.aws_caller_identity.current.account_id}"
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
