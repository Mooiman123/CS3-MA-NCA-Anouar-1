resource "aws_security_group" "ec2_worker_sg" {
  name        = "${var.project_name}-worker-sg"
  description = "Allow SSM and RDP for worker EC2 instances"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow RDP from anywhere (test)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

output "worker_security_group_id" {
  value = aws_security_group.ec2_worker_sg.id
}
