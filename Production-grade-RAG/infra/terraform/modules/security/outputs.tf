output "sg_ssh_id" { value = aws_security_group.ssh.id }
output "sg_app_id" { value = aws_security_group.app.id }
output "sg_alb_id" { value = aws_security_group.alb.id }
