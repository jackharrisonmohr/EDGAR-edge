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
