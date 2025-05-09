resource "aws_ecr_repository" "score_repository" {
  name                 = "edgar-edge/score"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project     = "EDGAR-Edge"
    Component   = "ScoringService"
    Sprint      = "3"
    ManagedBy   = "Terraform"
  }
}

resource "aws_ecr_lifecycle_policy" "score_repository_lifecycle_policy" {
  repository = aws_ecr_repository.score_repository.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

output "ecr_repository_url" {
  description = "The URL of the ECR repository for the scoring service"
  value       = aws_ecr_repository.score_repository.repository_url
}
