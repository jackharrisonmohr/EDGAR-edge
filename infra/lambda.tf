resource "aws_lambda_function" "ingest_puller" {
  function_name    = "edgar-edge-ingest-puller"
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_ingest_role.arn
  filename         = "lambda_ingest.zip"                   # This will be created by the CI/CD pipeline
  source_code_hash = filebase64sha256("lambda_ingest.zip") # This will be updated by the CI/CD pipeline

  environment {
    variables = {
      RAW_BUCKET = aws_s3_bucket.edgar_edge_raw.id
      RSS_URL    = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom"
    }
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_event_rule" "ingest_schedule_rule" {
  name                = "edgar-edge-ingest-schedule-rule"
  description         = "Triggers the ingest Lambda function every minute"
  schedule_expression = "rate(1 minute)"
}

resource "aws_cloudwatch_event_target" "ingest_lambda_target" {
  rule      = aws_cloudwatch_event_rule.ingest_schedule_rule.name
  target_id = "IngestLambda"
  arn       = aws_lambda_function.ingest_puller.arn
}
