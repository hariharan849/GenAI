terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.name_prefix}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = { ManagedBy = "terraform" }
}

# Allows Systems Manager Session Manager (SSM shell access without SSH key)
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# AmazonSSMManagedInstanceCore does NOT grant ssm:GetParameter — add it explicitly
resource "aws_iam_role_policy" "ssm_read" {
  name = "${var.name_prefix}-ssm-read"
  role = aws_iam_role.ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:*:*:parameter/rag/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        # Scope to SSM-managed keys. Tighten to specific key ARN post-deploy if needed.
        Resource = "arn:aws:kms:*:*:alias/aws/ssm"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.name_prefix}-ec2-profile"
  role = aws_iam_role.ec2.name
}
