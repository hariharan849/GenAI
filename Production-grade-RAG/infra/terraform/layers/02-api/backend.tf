terraform {
  backend "s3" {
    bucket         = "REPLACE_WITH_BUCKET_NAME"
    key            = "dev/api.tfstate"
    region         = "us-east-1"
    dynamodb_table = "rag-terraform-lock"
    encrypt        = true
  }
}
