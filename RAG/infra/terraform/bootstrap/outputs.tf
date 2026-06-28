output "state_bucket_name" {
  description = "Copy this into each layers/0N-*/backend.tf as a literal string"
  value       = aws_s3_bucket.tf_state.bucket
}

output "lock_table_name" {
  description = "Copy this into each layers/0N-*/backend.tf as a literal string"
  value       = aws_dynamodb_table.tf_lock.name
}
