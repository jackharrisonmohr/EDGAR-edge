resource "aws_ecs_cluster" "main" {
  name = "edgar-edge-cluster"

  tags = {
    Project   = "EDGAR-Edge"
    Sprint    = "3"
    ManagedBy = "Terraform"
  }
}

resource "aws_ecs_task_definition" "score_task" {
  family                   = "edgar-edge-score-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"  # 0.5 vCPU
  memory                   = "1024" # 1 GiB

  execution_role_arn = aws_iam_role.ecs_task_execution_role.arn # Assuming this role is defined elsewhere (e.g., iam.tf)

  container_definitions = jsonencode([{
    name      = "score-container"
    image     = "${aws_ecr_repository.score_repository.repository_url}:latest" # Will be updated by CI/CD
    essential = true
    portMappings = [{
      containerPort = 80
      hostPort      = 80
    }]
    environment = [
      {
        name  = "MODEL_S3_URI"
        value = "s3://your-model-bucket/path/to/your/model/" # Placeholder, update as needed
      },
      {
        name  = "RAW_BUCKET"                # For S3 fetch layer in app.py
        value = var.raw_filings_bucket_name # Assuming this var will hold the raw filings bucket name
      },
      {
        name  = "FARGATE_CPU" # For gunicorn_conf.py to adjust workers
        value = "512"         # Corresponds to 0.5 vCPU defined for the task
      },
      {
        name  = "USE_REAL_MODEL"
        value = "false" # Default to dummy model, can be overridden for deployed service
      },
      {
        name  = "LOCAL_MODEL_PATH"
        value = "/app/model_checkpoint" # Default local path for the model in the container
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/edgar-edge-score-task"
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  tags = {
    Project   = "EDGAR-Edge"
    Sprint    = "3"
    ManagedBy = "Terraform"
  }
}

resource "aws_cloudwatch_log_group" "score_task_logs" {
  name = "/ecs/edgar-edge-score-task"

  tags = {
    Project   = "EDGAR-Edge"
    Sprint    = "3"
    ManagedBy = "Terraform"
  }
}

resource "aws_ecs_service" "score_service" {
  name            = "edgar-edge-score-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.score_task.arn
  launch_type     = "FARGATE"
  desired_count   = 0 # Start with 0, will be managed by autoscaling

  network_configuration {
    subnets          = var.private_subnets                    # Assuming private_subnets is defined in vars.tf
    security_groups  = [aws_security_group.ecs_service_sg.id] # Assuming ecs_service_sg is defined
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.score_tg.arn
    container_name   = "score-container"
    container_port   = 80
  }

  depends_on = [aws_lb_target_group.score_tg] # Ensure target group exists before service

  tags = {
    Project   = "EDGAR-Edge"
    Sprint    = "3"
    ManagedBy = "Terraform"
  }
}

# Autoscaling for the Fargate service
resource "aws_appautoscaling_target" "ecs_service_scaling_target" {
  max_capacity       = 1
  min_capacity       = 0
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.score_service.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Dummy security group and target group for now, will be properly defined in INF-3.3
resource "aws_security_group" "ecs_service_sg" {
  name        = "edgar-edge-ecs-service-sg"
  description = "Security group for ECS Fargate service"
  vpc_id      = var.vpc_id # Assuming vpc_id is defined in vars.tf

  tags = {
    Project   = "EDGAR-Edge"
    Sprint    = "3"
    ManagedBy = "Terraform"
  }
}

resource "aws_lb_target_group" "score_tg" {
  name        = "edgar-edge-score-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id # Assuming vpc_id is defined in vars.tf
  target_type = "ip"

  health_check {
    path                = "/health" # Assuming a /health endpoint in the app
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }

  tags = {
    Project   = "EDGAR-Edge"
    Sprint    = "3"
    ManagedBy = "Terraform"
  }
}

data "aws_region" "current" {}

# Assumes an IAM role for ECS task execution is defined.
# If not, it should be created. Example:
# resource "aws_iam_role" "ecs_task_execution_role" {
#   name = "ecs_task_execution_role"
#   assume_role_policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Action = "sts:AssumeRole"
#       Effect = "Allow"
#       Principal = {
#         Service = "ecs-tasks.amazonaws.com"
#       }
#     }]
#   })
#   managed_policy_arns = [
#     "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
#   ]
# }
