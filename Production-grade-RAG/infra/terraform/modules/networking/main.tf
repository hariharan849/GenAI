terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "rag" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_subnet" "public_az1" {
  vpc_id                  = aws_vpc.rag.id
  cidr_block              = var.subnet_cidr_az1
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags = { Name = "${var.name_prefix}-public-az1" }
}

resource "aws_subnet" "public_az2" {
  vpc_id                  = aws_vpc.rag.id
  cidr_block              = var.subnet_cidr_az2
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true
  tags = { Name = "${var.name_prefix}-public-az2" }
}

resource "aws_internet_gateway" "rag" {
  vpc_id = aws_vpc.rag.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.rag.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.rag.id
  }
  tags = { Name = "${var.name_prefix}-public-rt" }
}

resource "aws_route_table_association" "az1" {
  subnet_id      = aws_subnet.public_az1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "az2" {
  subnet_id      = aws_subnet.public_az2.id
  route_table_id = aws_route_table.public.id
}
