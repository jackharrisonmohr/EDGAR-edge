# SQS FIFO Queue for filings needing sentiment scoring
# and associated Dead Letter Queue (DLQ)

resource "aws_sqs_queue" "score_queue_dlq" {
  name = "${var.project_name}-score-queue-dlq.fifo"
  tags = merge(var.tags, {
    Name = "${var.project_name}-score-queue-dlq.fifo"
  })

  # FIFO attributes
  fifo_queue = true

  # Encryption
  kms_master_key_id = "alias/aws/sqs" # Use AWS-managed key

  # Retention period (e.g., 14 days)
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "score_queue" {
  name = "${var.project_name}-score-queue.fifo"
  tags = merge(var.tags, {
    Name = "${var.project_name}-score-queue.fifo"
  })

  # FIFO attributes
  fifo_queue                  = true
  content_based_deduplication = false # We will provide MessageDeduplicationId

  # Visibility timeout (adjust based on expected processing time)
  visibility_timeout_seconds = 300 # 5 minutes

  # Encryption
  kms_master_key_id = "alias/aws/sqs"

  # Dead Letter Queue configuration
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.score_queue_dlq.arn
    maxReceiveCount     = 5 # Number of times a message is delivered before moving to DLQ
  })

  # Dependencies
  depends_on = [aws_sqs_queue.score_queue_dlq]
}

output "score_queue_url" {
  description = "The URL of the SQS queue for scoring filings"
  value       = aws_sqs_queue.score_queue.id # .id gives the URL
}

output "score_queue_arn" {
  description = "The ARN of the SQS queue for scoring filings"
  value       = aws_sqs_queue.score_queue.arn
}

output "score_queue_dlq_url" {
  description = "The URL of the SQS DLQ for the scoring queue"
  value       = aws_sqs_queue.score_queue_dlq.id
}

output "score_queue_dlq_arn" {
  description = "The ARN of the SQS DLQ for the scoring queue"
  value       = aws_sqs_queue.score_queue_dlq.arn
}
