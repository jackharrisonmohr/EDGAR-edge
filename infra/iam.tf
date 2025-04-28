resource "aws_iam_role" "lambda_ingest_role" {
  name = "${var.project_name}-lambda-ingest-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_policy" "lambda_ingest_policy" {
  name = "${var.project_name}-lambda-ingest-policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
      {
        Action = [
          "s3:PutObject"
        ],
        Effect   = "Allow",
        Resource = "${aws_s3_bucket.raw_filings.arn}/raw/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ingest_policy_attachment" {
  role       = aws_iam_role.lambda_ingest_role.name
  policy_arn = aws_iam_policy.lambda_ingest_policy.arn
}

resource "aws_cloudwatch_log_group" "ingest_lambda_log_group" {
  name = "/aws/lambda/edgar-edge-ingest-puller"
  retention_in_days = 7
}
