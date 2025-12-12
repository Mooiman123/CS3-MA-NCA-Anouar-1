#############################################
# OIDC Provider for EKS (IRSA core)
#############################################

data "aws_eks_cluster" "eks" {
  name = aws_eks_cluster.this.name
}

data "aws_eks_cluster_auth" "eks" {
  name = aws_eks_cluster.this.name
}

resource "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.eks.identity[0].oidc[0].issuer

  client_id_list = ["sts.amazonaws.com"]

  thumbprint_list = ["9e99a48a9960b14926bb7f3b02e22da0afd10df3"]

  tags = {
    Project = var.project_name
  }
}

#############################################
# BACKEND IRSA ROLE
#############################################

data "aws_iam_policy_document" "backend_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:default:backend-sa"]
    }
  }
}

resource "aws_iam_role" "backend_role" {
  name               = "${var.project_name}-backend-irsa"
  assume_role_policy = data.aws_iam_policy_document.backend_assume.json
}

resource "aws_iam_policy" "backend_policy" {
  name = "${var.project_name}-backend-policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan"
        ],
        Effect   = "Allow",
        Resource = aws_dynamodb_table.employees.arn
      },
      {
        Action   = ["sqs:SendMessage"],
        Effect   = "Allow",
        Resource = aws_sqs_queue.onboarding_queue.arn
      },
      {
        Action   = ["events:PutEvents"],
        Effect   = "Allow",
        Resource = "arn:aws:events:${var.region}:${data.aws_caller_identity.current.account_id}:event-bus/default"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "backend_attach" {
  role       = aws_iam_role.backend_role.name
  policy_arn = aws_iam_policy.backend_policy.arn
}

#############################################
# JOB CONTROLLER IRSA ROLE
#############################################

data "aws_iam_policy_document" "job_controller_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:default:job-controller-sa"]
    }
  }
}

resource "aws_iam_role" "job_controller_role" {
  name               = "${var.project_name}-job-controller-irsa"
  assume_role_policy = data.aws_iam_policy_document.job_controller_assume.json
}

resource "aws_iam_policy" "job_controller_policy" {
  name = "${var.project_name}-job-controller-policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        Effect   = "Allow",
        Resource = aws_sqs_queue.onboarding_queue.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "job_controller_attach" {
  role       = aws_iam_role.job_controller_role.name
  policy_arn = aws_iam_policy.job_controller_policy.arn
}

#############################################
# JOB WORKER IRSA ROLE
#############################################

data "aws_iam_policy_document" "job_worker_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:default:job-worker-sa"]
    }
  }
}

resource "aws_iam_role" "job_worker_role" {
  name               = "${var.project_name}-job-worker-irsa"
  assume_role_policy = data.aws_iam_policy_document.job_worker_assume.json
}

resource "aws_iam_policy" "job_worker_policy" {
  name = "${var.project_name}-job-worker-policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # Allow S3 upload for RDP files
      {
        "Action": [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ],
        "Effect": "Allow",
        "Resource": [
          "arn:aws:s3:::${var.s3_bucket}",
          "arn:aws:s3:::${var.s3_bucket}/rdp/*"
        ]
      },
      # Allow Directory Service domain join (ds:CreateComputer)
      {
        "Action": [
          "ds:CreateComputer"
        ],
        "Effect": "Allow",
        "Resource": [
          "arn:aws:ds:${var.region}:${data.aws_caller_identity.current.account_id}:directory/*"
        ]
      },
      {
        "Action": [
          "ds:DescribeDirectories"
        ],
        "Effect": "Allow",
        "Resource": "*"
      },
      # Allow SendCommand on all EC2 instances (voor domain join etc)
      {
        "Action" : [
          "ssm:SendCommand"
        ],
        "Effect" : "Allow",
        "Resource" : [
          "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"
        ]
      },
      {
        Action = [
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:DeleteItem"
        ],
        Effect   = "Allow",
        Resource = aws_dynamodb_table.employees.arn
      },
      {
        Action = [
          "iam:CreateRole",
          "iam:AttachRolePolicy",
          "iam:CreateInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:GetRole",
          "iam:GetInstanceProfile",
          "iam:PassRole",
          "iam:PutRolePolicy",
          # deletion / cleanup actions the job-worker may need
          "iam:RemoveRoleFromInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:ListRolePolicies",
          "iam:DeleteRolePolicy",
          "iam:DeleteRole",
          "iam:DeletePolicy"
        ],
        Effect = "Allow",
        Resource = [
          "arn:aws:iam::*:role/employee-*",
          "arn:aws:iam::*:instance-profile/${var.project_name}*",
          "arn:aws:iam::*:instance-profile/employee-profile*",
          "arn:aws:iam::*:policy/*",
          "arn:aws:iam::aws:policy/*"
        ]
      },
      {
        Action = [
          "ec2:RunInstances",
          "ec2:CreateTags",
          "ec2:DescribeInstances",
          # allow termination of instances created for employees
          "ec2:TerminateInstances",
          "ec2:DescribeInstanceStatus"
        ],
        Effect   = "Allow",
        Resource = "*"
      },
      {
        Action   = [
          "ssm:GetParameter",
          "ssm:DescribeInstanceInformation"
        ],
        Effect   = "Allow",
        Resource = "*"
      },
      {
        Action = [
          "workspaces:CreateWorkspaces",
          "workspaces:DescribeWorkspaces",
          "workspaces:TerminateWorkspaces",
          "workspaces:CreateTags",
          "workspaces:DescribeWorkspaceDirectories",
          "workspaces:DescribeWorkspaceBundles",
          "workspaces:DescribeTags"
        ],
        Effect   = "Allow",
        Resource = "*"
      },
      {
        Action   = ["sns:Publish"],
        Effect   = "Allow",
        Resource = "arn:aws:sns:${var.region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Action = [
          "ssm:SendCommand",
          "ssm:GetCommandInvocation"
        ],
        Effect = "Allow",
        Resource = concat(
          compact([
            var.management_instance_id != "" ? "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${var.management_instance_id}" : null,
            aws_instance.management_windows.arn
          ]),
          [
            "arn:aws:ssm:${var.region}:*:document/AWS-RunPowerShellScript",
            "arn:aws:ssm:${var.region}:*:document/AWS-JoinDirectoryServiceDomain"
          ]
        )
      },
      {
        Action = [
          "ssm:ListCommandInvocations",
          "ssm:ListCommands"
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "job_worker_attach" {
  role       = aws_iam_role.job_worker_role.name
  policy_arn = aws_iam_policy.job_worker_policy.arn
}
