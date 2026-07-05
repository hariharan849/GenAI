variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "rag"
}

variable "admin_cidr" {
  description = "Your public IP in CIDR notation for SSH and admin port access. Example: 203.0.113.5/32"
  type        = string
}

variable "key_name" {
  description = "EC2 key pair name"
  type        = string
  default     = "rag-key"
}

variable "public_key_content" {
  description = "Contents of your SSH public key file"
  type        = string
}

variable "github_owner" {
  description = "GitHub username or org that owns the repo"
  type        = string
}

variable "github_repo" {
  description = "GitHub repo name (without owner prefix)"
  type        = string
  default     = "GenerativeAI"
}

variable "orchestrator_profile" {
  description = "docker compose profile to activate: prefect | airflow | dagster"
  type        = string
  default     = "prefect"
}

variable "github_pat_ssm_name" {
  description = "SSM parameter name for GitHub PAT (for private repos). Leave empty for public repos."
  type        = string
  default     = ""
}

variable "env_ssm_name" {
  description = "SSM parameter name storing the .env file contents"
  type        = string
  default     = "/rag/env"
}
