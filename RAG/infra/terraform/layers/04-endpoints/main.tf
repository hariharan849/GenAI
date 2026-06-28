terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

data "terraform_remote_state" "infra" {
  backend = "s3"
  config = {
    bucket         = var.state_bucket
    key            = "dev/infra.tfstate"
    region         = var.aws_region
    dynamodb_table = "rag-terraform-lock"
  }
}

data "terraform_remote_state" "api" {
  backend = "s3"
  config = {
    bucket         = var.state_bucket
    key            = "dev/api.tfstate"
    region         = var.aws_region
    dynamodb_table = "rag-terraform-lock"
  }
}

data "terraform_remote_state" "ui" {
  backend = "s3"
  config = {
    bucket         = var.state_bucket
    key            = "dev/ui.tfstate"
    region         = var.aws_region
    dynamodb_table = "rag-terraform-lock"
  }
}

locals {
  infra = data.terraform_remote_state.infra.outputs
  api   = data.terraform_remote_state.api.outputs
  ui    = data.terraform_remote_state.ui.outputs
}

resource "aws_lb" "rag" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [local.infra.sg_alb_id]
  subnets            = [local.infra.subnet_id_az1, local.infra.subnet_id_az2]

  tags = { Name = "${var.name_prefix}-alb", ManagedBy = "terraform" }
}

resource "aws_lb_target_group" "api" {
  name     = "${var.name_prefix}-api-tg"
  port     = 8083
  protocol = "HTTP"
  vpc_id   = local.infra.vpc_id

  # Boot takes 15-25 min; slow_start gives instances time to warm up before traffic
  slow_start = 900

  health_check {
    path                = "/api/v1/health"
    matcher             = "200"
    interval            = 60
    timeout             = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${var.name_prefix}-api-tg" }
}

resource "aws_lb_target_group" "ui" {
  name     = "${var.name_prefix}-ui-tg"
  port     = 3004
  protocol = "HTTP"
  vpc_id   = local.infra.vpc_id

  slow_start = 900

  health_check {
    path                = "/"
    matcher             = "200"
    interval            = 60
    timeout             = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${var.name_prefix}-ui-tg" }
}

resource "aws_lb_target_group_attachment" "api" {
  target_group_arn = aws_lb_target_group.api.arn
  target_id        = local.api.api_instance_id
  port             = 8083
}

resource "aws_lb_target_group_attachment" "ui" {
  target_group_arn = aws_lb_target_group.ui.arn
  target_id        = local.ui.ui_instance_id
  port             = 3004
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.rag.arn
  port              = 80
  protocol          = "HTTP"

  # Default: forward to UI
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ui.arn
  }
}

# /api/* → FastAPI (all routes already at /api/v1/* in the codebase)
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  condition {
    path_pattern { values = ["/api/*"] }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
