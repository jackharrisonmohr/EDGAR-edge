resource "aws_lb" "score_alb" {
  name               = "${var.project_name}-score-alb"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = var.private_subnets # Ensure these are private subnets

  tags = merge(var.tags, {
    Name      = "${var.project_name}-score-alb"
    Sprint    = "3"
  })
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.score_alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.score_tg.arn # Defined in ecs.tf
  }
}

resource "aws_security_group" "alb_sg" {
  name        = "${var.project_name}-alb-sg"
  description = "Security group for the internal ALB for scoring service"
  vpc_id      = var.vpc_id

  ingress {
    description = "Allow HTTP from within VPC"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block] # Allows from anywhere within the VPC
  }

  ingress {
    description     = "Allow HTTP from Lambda SG"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda_sg.id] # Allow from Lambda SG
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name   = "${var.project_name}-alb-sg"
    Sprint = "3"
  })
}

# Output for the ALB DNS name
output "alb_dns_name" {
  description = "The DNS name of the internal Application Load Balancer"
  value       = aws_lb.score_alb.dns_name
}
