# CS3 - Employee onboarding demo

This repository contains a demo/proof-of-concept that provisions per-employee resources with an EKS-based workflow, EventBridge → SQS → job pod → AWS resources (IAM, EC2, WorkSpaces, AD via SSM, DynamoDB).

## Deletion (cascade cleanup)

When a user clicks delete in the portal the behaviour has been changed to perform a safe, asynchronous cleanup:

- The backend marks the DynamoDB employee record with status `DELETING` and publishes an `employeeDeleted` EventBridge event.
- The Job Controller receives the event (via SQS) and starts a per-employee job with `ACTION=delete`.
- The job performs best-effort cleanup: AD user removal via SSM, terminating WorkSpaces, terminating EC2 instances with `employeeId` tag, and removing IAM roles/instance-profiles attached to the employee. If anything fails, the DynamoDB status is set to `DELETE_FAILED` and details are published to SNS.
- After successful cleanup the job deletes the DynamoDB item and sends an SNS notification confirming the delete.

This ensures the provisioning path (adding employees) is left intact and unchanged; the delete flow is asynchronous and best-effort to avoid blocking the portal UI while AWS resources are removed.

