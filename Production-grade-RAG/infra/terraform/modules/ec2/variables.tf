variable "instance_name" {
  description = "EC2 instance Name tag"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID to launch the instance in"
  type        = string
}

variable "security_group_ids" {
  description = "List of security group IDs to attach"
  type        = list(string)
}

variable "instance_profile_name" {
  description = "IAM instance profile name (not ARN)"
  type        = string
}

variable "key_name" {
  description = "EC2 key pair name"
  type        = string
}

variable "public_key_content" {
  description = "SSH public key content (e.g., file(\"~/.ssh/id_rsa.pub\"))"
  type        = string
}

variable "volume_gb" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 30
}

variable "user_data_rendered" {
  description = "Rendered user_data script (use templatefile() in the calling layer)"
  type        = string
  default     = ""
}
