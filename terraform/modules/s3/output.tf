output "bucket_name" {
  value = aws_s3_bucket.main.id
}

output "logs_bucket_name" {
  value = aws_s3_bucket.logs.id
}
