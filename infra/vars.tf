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
