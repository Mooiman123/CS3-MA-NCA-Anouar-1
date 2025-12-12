import json
import os
import time

import boto3
from kubernetes import client, config

AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
EMPLOYEE_TABLE_NAME = os.getenv("EMPLOYEE_TABLE_NAME", "cs3-nca-employees")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
JOB_WORKER_IMAGE = os.getenv("JOB_WORKER_IMAGE")
NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
JOB_SERVICE_ACCOUNT = os.getenv("JOB_SERVICE_ACCOUNT", "job-worker-sa")
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "300"))
JOB_BACKOFF_LIMIT = int(os.getenv("JOB_BACKOFF_LIMIT", "0"))
JOB_ACTIVE_DEADLINE_SECONDS = int(os.getenv("JOB_ACTIVE_DEADLINE_SECONDS", "900"))
EC2_INSTANCE_TYPE = os.getenv("EC2_INSTANCE_TYPE", "t3.micro")
EC2_SUBNET_ID = os.getenv("EC2_SUBNET_ID")
EC2_SECURITY_GROUP_ID = os.getenv("EC2_SECURITY_GROUP_ID")
AMI_SSM_PARAMETER = os.getenv(
    "AMI_SSM_PARAMETER",
    "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
)
INSTANCE_PROFILE_PREFIX = os.getenv("INSTANCE_PROFILE_PREFIX", "employee-profile")
IAM_MANAGED_POLICY_ARN = os.getenv(
    "IAM_MANAGED_POLICY_ARN", "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
)

if not SQS_QUEUE_URL:
    raise ValueError("SQS_QUEUE_URL environment variable is required")

if not JOB_WORKER_IMAGE:
    raise ValueError("JOB_WORKER_IMAGE environment variable is required")

sqs = boto3.client("sqs", region_name=AWS_REGION)

try:
    config.load_incluster_config()
except Exception:
    config.load_kube_config()

batch_api = client.BatchV1Api()


def create_onboarding_job(message: dict):
    """
    Create one Kubernetes Job per employee onboarding.
    """
    employee_id = message.get("employeeId")

    if not employee_id:
        print("[WARN] employeeId ontbreekt, skip message")
        return

    print(f"[INFO] Starting Job for employee {employee_id}")

    job_name = f"onboard-{str(employee_id)[:8]}-{int(time.time())}"

    env_vars = [
        client.V1EnvVar(name="EMPLOYEE_ID", value=str(employee_id)),
        client.V1EnvVar(name="ACTION", value=message.get("action", "onboard")),
        client.V1EnvVar(name="NAME", value=message.get("name", "")),
        client.V1EnvVar(name="EMAIL", value=message.get("email", "")),
        client.V1EnvVar(name="DEPARTMENT", value=message.get("department", "")),
        client.V1EnvVar(name="AWS_REGION", value=AWS_REGION),
        client.V1EnvVar(name="EMPLOYEE_TABLE_NAME", value=EMPLOYEE_TABLE_NAME),
        client.V1EnvVar(name="EC2_INSTANCE_TYPE", value=EC2_INSTANCE_TYPE),
        client.V1EnvVar(name="AMI_SSM_PARAMETER", value=AMI_SSM_PARAMETER),
        client.V1EnvVar(name="INSTANCE_PROFILE_PREFIX", value=INSTANCE_PROFILE_PREFIX),
        client.V1EnvVar(name="IAM_MANAGED_POLICY_ARN", value=IAM_MANAGED_POLICY_ARN),
        client.V1EnvVar(name="SNS_TOPIC_ARN", value=os.getenv("SNS_TOPIC_ARN", "")),
        client.V1EnvVar(name="WORKSPACES_DIRECTORY_ID", value=os.getenv("WORKSPACES_DIRECTORY_ID", "")),
        client.V1EnvVar(name="WORKSPACES_BUNDLE_ID", value=os.getenv("WORKSPACES_BUNDLE_ID", "")),
        client.V1EnvVar(name="WORKSPACES_SUBNET_IDS", value=os.getenv("WORKSPACES_SUBNET_IDS", "")),
        client.V1EnvVar(name="AD_LDAP_URL", value=os.getenv("AD_LDAP_URL", "")),
        client.V1EnvVar(name="AD_BIND_DN", value=os.getenv("AD_BIND_DN", "")),
        client.V1EnvVar(name="AD_BIND_PASSWORD", value=os.getenv("AD_BIND_PASSWORD", "")),
        client.V1EnvVar(name="AD_BASE_DN", value=os.getenv("AD_BASE_DN", "")),
        client.V1EnvVar(name="AD_USER_OU", value=os.getenv("AD_USER_OU", "")),
        client.V1EnvVar(name="AD_USER_PASSWORD", value=os.getenv("AD_USER_PASSWORD", "")),
        client.V1EnvVar(name="AD_USER_DOMAIN", value=os.getenv("AD_USER_DOMAIN", "")),
        client.V1EnvVar(name="AD_ADMIN_UPN", value=os.getenv("AD_ADMIN_UPN", "")),
        client.V1EnvVar(name="AD_ADMIN_PASSWORD", value=os.getenv("AD_ADMIN_PASSWORD", "")),
        client.V1EnvVar(name="AD_DOMAIN_NETBIOS", value=os.getenv("AD_DOMAIN_NETBIOS", "")),
        client.V1EnvVar(name="MANAGEMENT_INSTANCE_ID", value=os.getenv("MANAGEMENT_INSTANCE_ID", "")),
        client.V1EnvVar(name="AD_DEFAULT_PASSWORD", value=os.getenv("AD_DEFAULT_PASSWORD", "")),
    ]

    ws_id = message.get("workspaceId")
    if ws_id:
        env_vars.append(client.V1EnvVar(name="WORKSPACE_ID", value=str(ws_id)))

    if EC2_SUBNET_ID:
        env_vars.append(client.V1EnvVar(name="EC2_SUBNET_ID", value=EC2_SUBNET_ID))
    if EC2_SECURITY_GROUP_ID:
        env_vars.append(
            client.V1EnvVar(name="EC2_SECURITY_GROUP_ID", value=EC2_SECURITY_GROUP_ID)
        )

    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=job_name),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=JOB_TTL_SECONDS,
            backoff_limit=JOB_BACKOFF_LIMIT,
            active_deadline_seconds=JOB_ACTIVE_DEADLINE_SECONDS,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"job": "onboarding"}),
                spec=client.V1PodSpec(
                    service_account_name=JOB_SERVICE_ACCOUNT,
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="onboarding-worker",
                            image=JOB_WORKER_IMAGE,
                            image_pull_policy="Always",
                            env=env_vars,
                        )
                    ],
                ),
            ),
        ),
    )

    batch_api.create_namespaced_job(namespace=NAMESPACE, body=job)
    print(f"[INFO] Job created: {job_name}")


def poll_queue():
    print("[INFO] Job Controller is running.")
    print(f"Polling SQS: {SQS_QUEUE_URL}")

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10,
            )

            messages = resp.get("Messages", [])

            if not messages:
                continue

            for msg in messages:
                try:
                    body = json.loads(msg["Body"])

                    detail = body["detail"] if "detail" in body else body

                    print(
                        f"[INFO] Received event for employee {detail.get('employeeId')}"
                    )

                    create_onboarding_job(detail)

                except Exception as e:
                    print(f"[ERROR] Error: {e}")

                finally:
                    sqs.delete_message(
                        QueueUrl=SQS_QUEUE_URL,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )

        except Exception as e:
            print(f"[ERROR] Fatal polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    poll_queue()
