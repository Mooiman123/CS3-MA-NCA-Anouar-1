variable "workspaces_directory_admin_password" {
  description = "Admin password for the Simple AD directory used by WorkSpaces"
  type        = string
  sensitive   = true
}

# Create a Simple AD directory in the private subnets for WorkSpaces
resource "aws_directory_service_directory" "ws_microsoft_ad" {
  name       = "org.innovatech.com"
  short_name = "innovatech"
  password   = var.workspaces_directory_admin_password
  edition    = "Standard" # Microsoft AD (Standard edition)
  type       = "MicrosoftAD"

  lifecycle {
    prevent_destroy = true
  }

  vpc_settings {
    vpc_id     = aws_vpc.main.id
    subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  }
}

# Default WorkSpaces service role (required for registering the directory)
data "aws_iam_policy_document" "workspaces_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["workspaces.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "workspaces_default" {
  name               = "workspaces_DefaultRole"
  assume_role_policy = data.aws_iam_policy_document.workspaces_assume.json
}

resource "aws_iam_role_policy_attachment" "workspaces_service_access" {
  role       = aws_iam_role.workspaces_default.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonWorkSpacesServiceAccess"
}

resource "aws_iam_role_policy_attachment" "workspaces_self_service_access" {
  role       = aws_iam_role.workspaces_default.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonWorkSpacesSelfServiceAccess"
}

# Register the Microsoft AD directory for WorkSpaces
resource "aws_workspaces_directory" "ws_dir" {
  directory_id = aws_directory_service_directory.ws_microsoft_ad.id
  subnet_ids   = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  depends_on = [
    aws_iam_role.workspaces_default,
    aws_iam_role_policy_attachment.workspaces_service_access,
    aws_iam_role_policy_attachment.workspaces_self_service_access
  ]

  lifecycle {
    prevent_destroy = true
  }

  workspace_access_properties {
    device_type_windows  = "ALLOW"
    device_type_osx      = "ALLOW"
    device_type_ios      = "ALLOW"
    device_type_android  = "ALLOW"
    device_type_chromeos = "ALLOW"
    device_type_linux    = "ALLOW"
  }
}

# Persist IDs in SSM parameters for the worker to read/use if desired
resource "aws_ssm_parameter" "ws_directory_id" {
  name  = "/cs3/workspaces/directory_id"
  type  = "String"
  value = aws_workspaces_directory.ws_dir.directory_id
}

# Choose a WorkSpaces bundle (example: Standard with Windows 10 (Server 2019 based))
resource "aws_ssm_parameter" "ws_bundle_id" {
  name  = "/cs3/workspaces/bundle_id"
  type  = "String"
  value = "wsb-gk1wpk43z"
}

# Subnets to use for WorkSpaces (private subnets)
resource "aws_ssm_parameter" "ws_subnet_ids" {
  name  = "/cs3/workspaces/subnet_ids"
  type  = "String"
  value = "subnet-020c05c9ddb4354f9,subnet-02e608ced5e035512"
}
