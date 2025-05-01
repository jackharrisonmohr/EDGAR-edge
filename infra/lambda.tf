resource "aws_lambda_function" "ingest_puller" {
  function_name    = "edgar-edge-ingest-puller"
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_ingest_role.arn
  filename         = "../lambda_ingest.zip"                   # This will be created by the CI/CD pipeline
  source_code_hash = filebase64sha256("../lambda_ingest.zip") # This will be updated by the CI/CD pipeline
  timeout          = 30

  environment {
    variables = {
      RAW_BUCKET = aws_s3_bucket.raw_filings.id
      RSS_URL    = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom"
    }
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest_puller.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_schedule_rule.arn
}

resource "aws_cloudwatch_event_rule" "ingest_schedule_rule" {
  name                = "edgar-edge-ingest-schedule-rule"
  description         = "Triggers the ingest Lambda function every minute"
  schedule_expression = "rate(1 minute)"
}

# # “Daytime” rule: 10:00–21:00 UTC
# resource "aws_cloudwatch_event_rule" "edgar_day" {
#   name                = "edgar-poll-day"
#   schedule_expression = "cron(0/1 10-21 ? * MON-FRI *)"
# }

# # “Half-hour” tail rule for the 21:30 cutoff
# resource "aws_cloudwatch_event_rule" "edgar_tail" {
#   name                = "edgar-poll-tail"
#   schedule_expression = "cron(30/1 21 ? * MON-FRI *)"
# }

