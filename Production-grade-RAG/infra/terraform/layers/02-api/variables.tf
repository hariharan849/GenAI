variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "rag"
}

variable "state_bucket" {
  description = "S3 bucket name from bootstrap output"
  type        = string
}

variable "admin_cidr" {
  description = "Your public IP in CIDR notation. Example: 203.0.113.5/32"
  type        = string
}

variable "key_name" {
  type    = string
  default = "rag-key"
}

variable "public_key_content" {
  type = string
}

variable "github_owner" {
  type = string
}

variable "github_repo" {
  type    = string
  default = "GenerativeAI"
}

variable "github_pat_ssm_name" {
  type    = string
  default = ""
}

variable "env_ssm_name" {
  type    = string
  default = "/rag/env"
}
