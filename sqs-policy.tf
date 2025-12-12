resource "aws_sqs_queue_policy" "onboarding_allow_eventbridge" {
  queue_url = aws_sqs_queue.onboarding_queue.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid      = "AllowEventBridgeToSend"
        Effect   = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.onboarding_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.employee_created.arn
          }
        }
      }
    ]
  })
}
