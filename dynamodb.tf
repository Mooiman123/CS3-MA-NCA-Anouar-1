resource "aws_dynamodb_table" "employees" {
  name         = "${var.project_name}-employees"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "employeeId"

  attribute {
    name = "employeeId"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_dynamodb_table" "employee_passwords" {
  name         = "${var.project_name}-employee-passwords"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "employeeId"

  attribute {
    name = "employeeId"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}
