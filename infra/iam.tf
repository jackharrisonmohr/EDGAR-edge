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

resource "aws_security_group" "lambda_sg" {
  name        = "${var.project_name}-lambda-sg"
  description = "Security group for the ingest Lambda function"
  vpc_id      = var.vpc_id

  # Allow outbound HTTPS to call ALB and other AWS services
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow outbound HTTP (though ALB is HTTPS, other services might be HTTP)
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow all outbound traffic for simplicity in this context, can be tightened
  # egress {
  #   from_port   = 0
  #   to_port     = 0
  #   protocol    = "-1"
  #   cidr_blocks = ["0.0.0.0/0"]
  # }

  tags = merge(var.tags, {
    Name   = "${var.project_name}-lambda-sg"
    Sprint = "3" # Assuming this SG is part of Sprint 3 work
  })
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
      },
      {
        Action = [
          "sqs:SendMessage"
        ],
        Effect   = "Allow",
        Resource = aws_sqs_queue.score_queue.arn # Reference the ARN from sqs.tf
      },
      {
        Action = [
          "dynamodb:PutItem"
          # Potentially add UpdateItem, GetItem if needed later for more complex logic
        ],
        Effect   = "Allow",
        Resource = aws_dynamodb_table.filing_dedupe.arn # Reference the ARN from dynamodb.tf
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ingest_policy_attachment" {
  role       = aws_iam_role.lambda_ingest_role.name
  policy_arn = aws_iam_policy.lambda_ingest_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access_attachment" {
  role       = aws_iam_role.lambda_ingest_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_cloudwatch_log_group" "ingest_lambda_log_group" {
  name              = "/aws/lambda/edgar-edge-ingest-puller"
  retention_in_days = 7
}

resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  managed_policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
  ]

  tags = var.tags
}
