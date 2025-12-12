resource "aws_sns_topic" "onboarding_notifications" {
  name = "${var.project_name}-onboarding-notifications"
}

# Optioneel: e-mail subscription, vul je adres in of verwijder dit blok
resource "aws_sns_topic_subscription" "onboarding_email" {
  topic_arn = aws_sns_topic.onboarding_notifications.arn
  protocol  = "email"
  endpoint  = "559155@student.fontys.nl"
}
