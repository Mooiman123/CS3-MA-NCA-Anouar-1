resource "aws_sqs_queue" "onboarding_queue" {
  name = "${var.project_name}-onboarding-queue"

  visibility_timeout_seconds = 30

  tags = {
    Project = var.project_name
  }
}
