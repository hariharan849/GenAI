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
