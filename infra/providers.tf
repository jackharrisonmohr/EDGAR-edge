terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # Specify a suitable version constraint
    }
  }

  # Using local state initially as per sprint1.md
  # To use S3 backend later, uncomment and configure:
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket-name" # Replace with your bucket name
  #   key            = "edgar-edge/terraform.tfstate"
  #   region         = "us-east-1" # Or your preferred region
  #   encrypt        = true
  #   dynamodb_table = "your-terraform-lock-table" # Optional: for state locking
  # }
}

provider "aws" {
  region = var.aws_region
}
