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

locals {
  infra = data.terraform_remote_state.infra.outputs
}

module "ec2" {
  source = "../../modules/ec2"

  instance_name         = "${var.name_prefix}-api"
  instance_type         = "t3.large"
  volume_gb             = 60
  subnet_id             = local.infra.subnet_id_az1
  security_group_ids    = [local.infra.sg_ssh_id, local.infra.sg_app_id]
  instance_profile_name = local.infra.instance_profile_name
  key_name              = var.key_name
  public_key_content    = var.public_key_content

  user_data_rendered = templatefile("${path.module}/user_data.sh.tpl", {
    aws_region          = var.aws_region
    github_owner        = var.github_owner
    github_repo         = var.github_repo
    github_pat_ssm_name = var.github_pat_ssm_name
    env_ssm_name        = var.env_ssm_name
    infra_private_ip    = local.infra.infra_private_ip
  })
}
