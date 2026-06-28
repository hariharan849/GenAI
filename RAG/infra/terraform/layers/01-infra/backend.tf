terraform {
  backend "s3" {
    # IMPORTANT: Copy the bucket name from `terraform output state_bucket_name`
    # after running bootstrap. Variable interpolation is NOT allowed here.
    bucket         = "REPLACE_WITH_BUCKET_NAME"
    key            = "dev/infra.tfstate"
    region         = "us-east-1"
    dynamodb_table = "rag-terraform-lock"
    encrypt        = true
  }
}
