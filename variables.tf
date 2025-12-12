variable "s3_bucket" {
  description = "S3 bucket voor RDP-bestanden"
  type        = string
}
variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "management_instance_id" {
  description = "Management Windows instance ID for SSM password resets"
  type        = string
  default     = ""
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "cs3-nca"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "cs3-nca-eks"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "worker_security_group_id" {
  description = "Security group ID for worker EC2 instances"
  type        = string
  default     = ""
}
