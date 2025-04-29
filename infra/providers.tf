terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "edgar-edge-tfstate-617597922955-us-east-1"
    key            = "terraform.tfstate" # Keep the state file name consistent
    region         = "us-east-1"
    dynamodb_table = "edgar-edge-tfstate-lock"
    encrypt        = true # Ensure state file encryption at rest
  }
}

provider "aws" {
  region = var.aws_region
  # Configuration options
}
