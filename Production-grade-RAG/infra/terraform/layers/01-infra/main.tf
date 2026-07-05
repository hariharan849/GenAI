terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source = "../../modules/networking"

  name_prefix     = var.name_prefix
  vpc_cidr        = "10.0.0.0/16"
  subnet_cidr_az1 = "10.0.1.0/24"
  subnet_cidr_az2 = "10.0.2.0/24"
}

module "security" {
  source = "../../modules/security"

  name_prefix = var.name_prefix
  vpc_id      = module.networking.vpc_id
  vpc_cidr    = module.networking.vpc_cidr
  admin_cidr  = var.admin_cidr
}

module "iam" {
  source      = "../../modules/iam"
  name_prefix = var.name_prefix
}

module "ec2" {
  source = "../../modules/ec2"

  instance_name         = "${var.name_prefix}-infra"
  instance_type         = "t3.xlarge"
  volume_gb             = 80
  subnet_id             = module.networking.subnet_id_az1
  security_group_ids    = [module.security.sg_ssh_id, module.security.sg_app_id]
  instance_profile_name = module.iam.instance_profile_name
  key_name              = var.key_name
  public_key_content    = var.public_key_content

  user_data_rendered = templatefile("${path.module}/user_data.sh.tpl", {
    aws_region           = var.aws_region
    github_owner         = var.github_owner
    github_repo          = var.github_repo
    orchestrator_profile = var.orchestrator_profile
    github_pat_ssm_name  = var.github_pat_ssm_name
    env_ssm_name         = var.env_ssm_name
  })
}

# Guard: prevent accidental replacement (new private IP cascades to api+ui layers)
resource "null_resource" "infra_destroy_guard" {
  triggers = { instance_id = module.ec2.instance_id }

  lifecycle {
    prevent_destroy = true
  }
}
