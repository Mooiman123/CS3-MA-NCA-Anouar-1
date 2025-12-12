output "cluster_name" {
  value = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.employees.name
}

output "sqs_queue_url" {
  value = aws_sqs_queue.onboarding_queue.id
}

output "workspaces_directory_id" {
  value = aws_workspaces_directory.ws_dir.directory_id
}

output "workspaces_bundle_id" {
  value = aws_ssm_parameter.ws_bundle_id.value
  sensitive = true
}

output "workspaces_subnet_ids" {
  value = aws_ssm_parameter.ws_subnet_ids.value
  sensitive = true
}

output "s3_bucket" {
  value = var.s3_bucket
}

output "public_subnet_a_id" {
  value = aws_subnet.public_a.id
}

output "public_subnet_b_id" {
  value = aws_subnet.public_b.id
}
