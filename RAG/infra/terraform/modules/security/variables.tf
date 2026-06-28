variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block — used for intra-VPC ingress rule"
  type        = string
}

variable "admin_cidr" {
  description = "Your IP in CIDR notation for SSH and admin port access. Example: 203.0.113.5/32"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
  default     = "rag"
}
