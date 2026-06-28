output "vpc_id"          { value = aws_vpc.rag.id }
output "vpc_cidr"        { value = aws_vpc.rag.cidr_block }
output "subnet_id_az1"   { value = aws_subnet.public_az1.id }
output "subnet_id_az2"   { value = aws_subnet.public_az2.id }
