# S3 bucket for storing deployment artifacts (e.g., Lambda zip files)

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.project_name}-artifacts-${data.aws_caller_identity.current.account_id}" # Ensure unique bucket name

  tags = merge(var.tags, {
    Name = "${var.project_name}-artifacts"
  })
}

# Block all public access for the artifacts bucket
resource "aws_s3_bucket_public_access_block" "artifacts_public_access_block" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning for the artifacts bucket
resource "aws_s3_bucket_versioning" "artifacts_versioning" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption by default
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts_sse_config" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Data source to get the current AWS account ID for unique bucket naming
data "aws_caller_identity" "current" {}

output "artifacts_bucket_name" {
  description = "The name of the S3 bucket used for storing deployment artifacts"
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifacts_bucket_arn" {
  description = "The ARN of the S3 bucket used for storing deployment artifacts"
  value       = aws_s3_bucket.artifacts.arn
}

# Removed aws_account_id output as it's now fetched via AWS CLI in the workflow
