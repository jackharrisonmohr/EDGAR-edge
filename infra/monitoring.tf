# CloudWatch Alarms for monitoring the SQS score queue

resource "aws_cloudwatch_metric_alarm" "sqs_score_queue_age_warning" {
  alarm_name          = "${var.project_name}-score-queue-age-warning"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1" # Evaluate over 1 period
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = "60" # Check every 60 seconds
  statistic           = "Maximum"
  threshold           = "60" # Warn if oldest message is >= 60 seconds old
  alarm_description   = "Warning: SQS score queue messages are getting old (>= 60s)."
  treat_missing_data  = "notBreaching" # Treat missing data as OK

  dimensions = {
    QueueName = aws_sqs_queue.score_queue.name
  }

  # Optional: Add SNS topic ARN for notifications
  # alarm_actions = [aws_sns_topic.alarms.arn]
  # ok_actions    = [aws_sns_topic.alarms.arn]

  tags = merge(var.tags, {
    Name      = "${var.project_name}-score-queue-age-warning"
    Severity  = "Warning"
  })
}

resource "aws_cloudwatch_metric_alarm" "sqs_score_queue_age_critical" {
  alarm_name          = "${var.project_name}-score-queue-age-critical"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1" # Evaluate over 1 period
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = "60" # Check every 60 seconds
  statistic           = "Maximum"
  threshold           = "300" # Critical if oldest message is >= 300 seconds (5 min) old
  alarm_description   = "CRITICAL: SQS score queue messages are very old (>= 300s). Processing might be stuck."
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.score_queue.name
  }

  # Optional: Add SNS topic ARN for notifications
  # alarm_actions = [aws_sns_topic.alarms.arn]
  # ok_actions    = [aws_sns_topic.alarms.arn]

  tags = merge(var.tags, {
    Name      = "${var.project_name}-score-queue-age-critical"
    Severity  = "Critical"
  })
}
