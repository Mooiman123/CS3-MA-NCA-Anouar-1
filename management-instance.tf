#############################################
# Windows management instance for AD user password reset via SSM
#############################################

variable "management_key_name" {
  description = "Optional EC2 key pair name for the management Windows instance (for RDP). Leave empty to use SSM only."
  type        = string
  default     = ""
}

# IAM role for SSM access
resource "aws_iam_role" "management_ssm_role" {
  name = "${var.project_name}-mgmt-ssm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "ec2.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "management_ssm_core" {
  role       = aws_iam_role.management_ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "management_ssm_ds" {
  role       = aws_iam_role.management_ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMDirectoryServiceAccess"
}

resource "aws_iam_instance_profile" "management_ssm_profile" {
  name = "${var.project_name}-mgmt-ssm-profile"
  role = aws_iam_role.management_ssm_role.name
}

# Security group for management instance
resource "aws_security_group" "management_sg" {
  name        = "${var.project_name}-mgmt-sg"
  description = "SG for management Windows instance (RDP + SSM)"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  # SMB/Windows file sharing openzetten voor test
  ingress {
    from_port   = 445
    to_port     = 445
    protocol    = "tcp"
    cidr_blocks = ["10.0.11.0/24", "10.0.12.0/24"]
  }
}

# Latest Windows Server 2022 base AMI
data "aws_ami" "windows" {
  most_recent = true
  owners      = ["801119661308"] # Amazon

  filter {
    name   = "name"
    values = ["Windows_Server-2022-English-Full-Base-*"]
  }
}

resource "aws_instance" "management_windows" {
  ami                    = data.aws_ami.windows.id
  instance_type          = "t3.large"
  # Plaats management host in public subnet zodat hij directe outbound/inbound connectiviteit heeft
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.management_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.management_ssm_profile.name

  associate_public_ip_address = true
  key_name                    = var.management_key_name != "" ? var.management_key_name : null

  tags = {
    Name    = "${var.project_name}-mgmt"
    Project = var.project_name
  }
}

output "management_instance_id" {
  value       = aws_instance.management_windows.id
  description = "Management Windows instance ID (domain join via SSM needed)"
}
