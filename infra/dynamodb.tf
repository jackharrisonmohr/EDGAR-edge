# DynamoDB table for deduplicating filings processed by the ingest lambda

resource "aws_dynamodb_table" "filing_dedupe" {
  name         = "${var.project_name}-filing-dedupe"
  billing_mode = "PAY_PER_REQUEST" # Suitable for unpredictable workloads
  hash_key     = "accession_no"

  attribute {
    name = "accession_no"
    type = "S" # String
  }

  # Enable Time To Live (TTL) for automatic cleanup
  ttl {
    attribute_name = "ttl" # Name of the attribute storing the expiration timestamp
    enabled        = true
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-filing-dedupe"
  })
}

output "filing_dedupe_table_name" {
  description = "The name of the DynamoDB table used for filing deduplication"
  value       = aws_dynamodb_table.filing_dedupe.name
}

output "filing_dedupe_table_arn" {
  description = "The ARN of the DynamoDB table used for filing deduplication"
  value       = aws_dynamodb_table.filing_dedupe.arn
}
