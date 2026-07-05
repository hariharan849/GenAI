variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
  default     = "rag"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr_az1" {
  description = "CIDR for public subnet in AZ1"
  type        = string
  default     = "10.0.1.0/24"
}

variable "subnet_cidr_az2" {
  description = "CIDR for public subnet in AZ2"
  type        = string
  default     = "10.0.2.0/24"
}
