variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "The base name for project resources."
  type        = string
  default     = "edgar-edge"
}

variable "tags" {
  description = "A map of tags to assign to resources."
  type        = map(string)
  default = {
    Project   = "EDGAR-Edge"
    ManagedBy = "Terraform"
  }
}

variable "lambda_zip_s3_key" {
  description = "The S3 key for the Lambda function deployment package."
  type        = string
  # No default, this must be provided during apply (e.g., by CI/CD)
}

variable "lambda_zip_s3_version" {
  description = "The S3 object version for the Lambda function deployment package."
  type        = string
  default     = null # Optional, only needed if S3 versioning is used for the artifact
}

variable "vpc_id" {
  description = "The ID of the VPC where resources will be deployed."
  type        = string
  default     = "vpc-01e8b89a1eeb904f7" #should be configured per environment
}

variable "private_subnets" {
  description = "A list of private subnet IDs for Fargate tasks and other resources."
  type        = list(string)
  default     = ["subnet-0a9310564ba98d6c9"] # should be configured per environment
}

variable "vpc_cidr_block" {
  description = "The CIDR block for the VPC."
  type        = string
  default     = "172.31.0.0/16" # Pshould be configured per environment
}

variable "raw_filings_bucket_name" {
  description = "The name of the S3 bucket for raw filings."
  type        = string
  default     = "edgar-edge-raw" # Default, ensure this matches s3.tf or is overridden
}
