output "alb_dns_name" {
  description = "Public URL for the entire stack — set this as your bookmark"
  value       = aws_lb.rag.dns_name
}

output "alb_arn" { value = aws_lb.rag.arn }
