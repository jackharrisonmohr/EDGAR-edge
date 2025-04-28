output "raw_bucket_name" {
  description = "The name of the raw filings S3 bucket"
  value       = aws_s3_bucket.edgar_edge_raw.id
}

output "ingest_lambda_arn" {
  description = "The ARN of the ingest Lambda function"
  value       = aws_lambda_function.ingest_puller.arn
}
