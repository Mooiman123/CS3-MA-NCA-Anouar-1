resource "aws_cloudwatch_event_rule" "employee_created" {
  name        = "${var.project_name}-employee-created"
  description = "Rule for employee created events"

  event_pattern = jsonencode({
    source        = ["eks.backend"]
    "detail-type" = ["employeeCreated", "employeeDeleted"]
  })

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_event_target" "to_sqs" {
  rule      = aws_cloudwatch_event_rule.employee_created.name
  arn       = aws_sqs_queue.onboarding_queue.arn
  target_id = "onboarding-sqs"
}
