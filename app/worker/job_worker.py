# === EC2 provisioning met domain join, AD-user, groep, en SNS met RDP-bestand ===
def create_ec2_for_employee(employee_id: str, email: str, department: str) -> dict:
    user_name = email.split("@")[0] if email else f"user-{employee_id}"
    password = generate_password()
    store_employee_password(employee_id, email, password)
    dept = (department or "").lower()

    # User data script voor software-installatie
    if dept == "hr":
        software_block = '''
        $ffUrl  = "https://download.mozilla.org/?product=firefox-latest&os=win64&lang=en-US"
        $ffPath = "C:\\Temp\\firefox-setup.exe"
        Invoke-WebRequest -Uri $ffUrl -OutFile $ffPath
        Start-Process -FilePath $ffPath -ArgumentList "/S" -Wait
        '''
    elif dept == "it":
        software_block = '''
        $puttyUrl  = "https://the.earth.li/~sgtatham/putty/latest/w64/putty-64bit-installer.msi"
        $puttyPath = "C:\\Temp\\putty-installer.msi"
        Invoke-WebRequest -Uri $puttyUrl -OutFile $puttyPath
        Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$puttyPath`" /qn" -Wait
        '''
    else:
        software_block = 'Write-Host "No extra software configured for department"'

    # Zorg dat AD RSAT tools aanwezig zijn zodat Get-ADUser / Add-ADGroupMember werken in latere SSM scripts
    user_data = f'''<powershell>
    New-Item -ItemType Directory -Path "C:\\Temp" -Force | Out-Null
    # Installeer AD RSAT PowerShell module
    try {{
        Add-WindowsCapability -Online -Name "Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0" -ErrorAction Stop | Out-Null
    }} catch {{
        Install-WindowsFeature RSAT-AD-PowerShell -IncludeAllSubFeature -IncludeManagementTools | Out-Null
    }}
    Import-Module ActiveDirectory -ErrorAction SilentlyContinue
    {software_block}
</powershell>'''

    # Zorg dat het instance profile bestaat en gebruik deze
    _, profile_name, _ = ensure_instance_role(employee_id)
    time.sleep(5)  # IAM propagatie
    # Launch EC2 instance in public subnet with public IP
    instance = ec2.run_instances(
        ImageId="ami-0852a4ffb1d7b687f",  # Hardcoded Windows Server 2022 AMI
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        SubnetId=SUBNET_ID,
        SecurityGroupIds=[SECURITY_GROUP_ID],
        IamInstanceProfile={"Name": profile_name},
        UserData=user_data,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "employeeId", "Value": employee_id},
                    {"Key": "Project", "Value": "cs3-nca"},
                    {"Key": "Department", "Value": dept},
                ],
            }
        ],
    )["Instances"][0]
    instance_id = instance["InstanceId"]
    print(f"[EC2] Instance created: {instance_id}")

    # Wacht tot running
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print(f"[EC2] Instance {instance_id} is running")

    # Wacht tot SSM agent online zodat domain join kan slagen
    wait_seconds = int(os.getenv("SSM_AGENT_WAIT_SECONDS", "900"))  # standaard 15 minuten
    deadline = time.time() + max(wait_seconds, 60)
    poll_interval = 10
    ssm_ready = False
    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            resp = ssm.describe_instance_information(
                Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
            )
        except ClientError as exc:
            print(f"[EC2] SSM describe failed (retrying): {exc}")
            continue
        info_list = resp.get("InstanceInformationList", [])
        if info_list and info_list[0].get("PingStatus") == "Online":
            print(f"[EC2] SSM agent online for {instance_id}")
            ssm_ready = True
            break
    if not ssm_ready:
        raise TimeoutError(f"[EC2] SSM agent did not come online in time for {instance_id}")

    # Domain join - robuuste workflow
    if not WS_DIRECTORY_ID or not AD_USER_DOMAIN:
        raise Exception(f"[EC2] Domain join parameters ontbreken: WS_DIRECTORY_ID={WS_DIRECTORY_ID}, AD_USER_DOMAIN={AD_USER_DOMAIN}")
    directory_info = ds_client.describe_directories(DirectoryIds=[WS_DIRECTORY_ID])
    descriptions = directory_info.get("DirectoryDescriptions", [])
    if not descriptions:
        raise Exception(f"[EC2] Directory {WS_DIRECTORY_ID} niet gevonden")
    dir_desc = descriptions[0]
    directory_name = dir_desc.get("Name") or AD_USER_DOMAIN
    if not directory_name:
        raise Exception(f"[EC2] Directory {WS_DIRECTORY_ID} heeft geen naam")
    if AD_USER_DOMAIN and directory_name and directory_name.lower() != AD_USER_DOMAIN.lower():
        print(f"[EC2] Waarschuwing: directory naam '{directory_name}' verschilt van AD_USER_DOMAIN '{AD_USER_DOMAIN}'")
    dns_ips = [ip for ip in dir_desc.get("DnsIpAddrs", []) if ip]
    directory_short_name = dir_desc.get("ShortName") or AD_DOMAIN_NETBIOS
    if not directory_short_name:
        print("[EC2] Waarschuwing: geen directory ShortName gevonden; gebruik fallback")
    else:
        print(f"[EC2] Directory ShortName gedetecteerd: {directory_short_name}")
    params = {
        "directoryId": [WS_DIRECTORY_ID],
        "directoryName": [directory_name],
    }
    if dns_ips:
        params["dnsIpAddresses"] = dns_ips

    join = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-JoinDirectoryServiceDomain",
        Parameters=params,
    )
    join_cmd_id = join["Command"]["CommandId"]
    print(f"[EC2] Domain join command sent: {join_cmd_id}")
    # Wacht tot domain join klaar is en check status
    for _ in range(30):
        time.sleep(10)
        resp = ssm.list_command_invocations(CommandId=join_cmd_id, Details=True)
        inv = resp.get("CommandInvocations", [])
        if inv and inv[0].get("Status") in ("Success", "Failed", "Cancelled", "TimedOut"): 
            print(f"[EC2] Domain join status: {inv[0]['Status']}")
            if inv[0]["Status"] != "Success":
                err = inv[0].get("StatusDetails") or inv[0].get("StandardErrorContent") or "Onbekende fout"
                raise Exception(f"[EC2] Domain join mislukt: {err}")
            break
    else:
        raise Exception(f"[EC2] Domain join timeout voor {instance_id}")

    # AD user aanmaken en aan groep toevoegen via management instance
    ad_ps = f'''
# Zorg dat RSAT AD tools aanwezig zijn en forceer een expliciete AD server
try {{
    Add-WindowsCapability -Online -Name "Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0" -ErrorAction Stop | Out-Null
}} catch {{
    Install-WindowsFeature RSAT-AD-PowerShell -IncludeAllSubFeature -IncludeManagementTools | Out-Null
}}
Import-Module ActiveDirectory -ErrorAction Stop
$Server      = "{AD_LDAP_URL}"; if (-not $Server) {{ $Server = "{AD_USER_DOMAIN}" }}
$Username    = "{user_name}"
$DisplayName = "Employee {employee_id} ({user_name})"
$Password    = "{password}"
$OuPath      = "{AD_USER_OU}"
$AdminUser   = "{AD_ADMIN_UPN}"
$AdminPass   = "{AD_ADMIN_PASSWORD}"
$secAdminPwd = ConvertTo-SecureString $AdminPass -AsPlainText -Force
$cred        = New-Object System.Management.Automation.PSCredential($AdminUser, $secAdminPwd)
$secureUserPwd = ConvertTo-SecureString $Password -AsPlainText -Force
New-ADUser -Server $Server -Name $DisplayName -SamAccountName $Username -UserPrincipalName "$Username@{AD_USER_DOMAIN}" -DisplayName $DisplayName -Path $OuPath -AccountPassword $secureUserPwd -Enabled $true -Credential $cred
Set-ADUser -Server $Server -Identity $Username -ChangePasswordAtLogon $false -Credential $cred
Add-ADGroupMember -Server $Server -Identity "Dept-{department.upper()}" -Members $Username -Credential $cred
'''
    ad_cmd = ssm.send_command(
        InstanceIds=[MANAGEMENT_INSTANCE_ID],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={"commands": [ad_ps]},
    )
    ad_cmd_id = ad_cmd["Command"]["CommandId"]
    print(f"[EC2] AD user/group command sent: {ad_cmd_id}")

    # Wacht tot AD user/group script klaar is zodat RDP membership kan slagen en fail hard op auth errors
    for _ in range(30):
        time.sleep(10)
        resp = ssm.list_command_invocations(CommandId=ad_cmd_id, Details=True)
        inv = resp.get("CommandInvocations", [])
        if inv and inv[0].get("Status") in ("Success", "Failed", "Cancelled", "TimedOut"):
            status = inv[0]["Status"]
            stdout = inv[0].get("StandardOutputContent") or ""
            stderr = inv[0].get("StandardErrorContent") or ""
            combined = (stdout + "\n" + stderr).strip()
            print(f"[EC2] AD user/group status: {status}")
            if status != "Success" or "AuthenticationException" in combined or "rejected the client credentials" in combined:
                err = combined or inv[0].get("StatusDetails") or "Onbekende fout"
                raise Exception(f"[EC2] AD user/group mislukt: {err}")
            break
    else:
        raise Exception(f"[EC2] AD user/group timeout voor command {ad_cmd_id}")

    # Voeg RDP-rechten lokaal toe zodat de nieuwe gebruiker kan inloggen
    rdp_ps = f'''
$ErrorActionPreference = "Stop"
$domain = "{AD_DOMAIN_NETBIOS}"
$user = "{user_name}"
$target = "$domain\\$user"
Add-LocalGroupMember -Group "Remote Desktop Users" -Member $target
try {{ Add-LocalGroupMember -Group "Administrators" -Member $target -ErrorAction Stop }} catch {{ Write-Host "Admin add skipped: $_" }}
net localgroup "Remote Desktop Users" $target
net localgroup Administrators $target
'''
    rdp_cmd = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={"commands": [rdp_ps]},
    )
    rdp_group_cmd_id = rdp_cmd["Command"]["CommandId"]
    print(f"[EC2] RDP rights command sent: {rdp_group_cmd_id}")
    for _ in range(30):
        time.sleep(5)
        resp = ssm.list_command_invocations(CommandId=rdp_group_cmd_id, Details=True)
        inv = resp.get("CommandInvocations", [])
        if inv and inv[0].get("Status") in ("Success", "Failed", "Cancelled", "TimedOut"):
            status = inv[0]["Status"]
            stdout = inv[0].get("StandardOutputContent") or ""
            stderr = inv[0].get("StandardErrorContent") or ""
            combined = (stdout + "\n" + stderr).strip()
            print(f"[EC2] RDP rights status: {status}")
            if status != "Success":
                raise Exception(f"[EC2] RDP rights mislukt: {combined or inv[0].get('StatusDetails') or 'Onbekende fout'}")
            break
    else:
        raise Exception(f"[EC2] RDP rights timeout voor command {rdp_group_cmd_id}")

    # Genereer RDP-bestand
    rdp_content = f'''full address:s:{instance.get('PublicDnsName','') or instance.get('PrivateIpAddress','')}:3389\nusername:s:{user_name}\n'''
    rdp_file = f"/tmp/{user_name}-{instance_id}.rdp"
    with open(rdp_file, "w") as f:
        f.write(rdp_content)


    # Upload RDP-bestand naar S3 en genereer downloadlink
    S3_BUCKET = os.getenv("S3_BUCKET", "cs1-terraform-state-anouar")
    rdp_url = None
    s3_upload_error = None
    if S3_BUCKET:
        try:
            s3 = boto3.client("s3")
            s3_key = f"rdp/{user_name}-{instance_id}.rdp"
            s3.upload_file(rdp_file, S3_BUCKET, s3_key)
            # Genereer een pre-signed URL voor download (24 uur geldig)
            rdp_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": s3_key},
                ExpiresIn=86400
            )
            print(f"[EC2] RDP file uploaded to S3: {rdp_url}")
        except Exception as exc:
            s3_upload_error = str(exc)
            print(f"[EC2] Failed to upload RDP to S3: {exc}")
    else:
        s3_upload_error = "S3_BUCKET environment variable not set"

    # SNS notificatie met downloadlink indien beschikbaar, anders foutmelding
    subject = f"Nieuwe EC2 voor medewerker: {user_name}"
    if rdp_url:
        rdp_info = f"RDP-bestand: {rdp_url}\n"
    else:
        rdp_info = f"RDP-bestand kon niet worden geüpload: {s3_upload_error or rdp_file}\n"

    message = (
        f"Nieuwe EC2 instance is aangemaakt voor {user_name}\n"
        f"InstanceId: {instance_id}\n"
        f"{rdp_info}"
        f"Gebruikersnaam: {user_name}\n"
        f"Wachtwoord: {password}\n"
        f"Domein: {AD_USER_DOMAIN}\n"
    )
    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    print(f"[EC2] SNS notification sent for {user_name}")

    # SNS notificatie met downloadlink indien beschikbaar
    subject = f"Nieuwe EC2 voor medewerker: {user_name}"
    message = (
        f"Nieuwe EC2 instance is aangemaakt voor {user_name}\n"
        f"InstanceId: {instance_id}\n"
        f"RDP-bestand: {rdp_url or rdp_file}\n"
        f"Gebruikersnaam: {user_name}\n"
        f"Wachtwoord: {password}\n"
        f"Domein: {AD_USER_DOMAIN}\n"
    )
    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    print(f"[EC2] SNS notification sent for {user_name}")

    return {
        "status": "ok",
        "employee_id": employee_id,
        "instance_id": instance_id,
        "user_name": user_name,
        "password": password,
        "rdp_file": rdp_file,
        "ad_cmd_id": ad_cmd_id,
        "join_cmd_id": join_cmd_id,
        "rdp_cmd_id": rdp_group_cmd_id,
    }
import json
import os
import time
from typing import Dict, Tuple

import boto3
from botocore.exceptions import ClientError

AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
AWS_ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID") or boto3.client("sts").get_caller_identity()["Account"]
TABLE_NAME = os.getenv("EMPLOYEE_TABLE_NAME", "cs3-nca-employees")
PASSWORD_TABLE_NAME = os.getenv("EMPLOYEE_PASSWORD_TABLE_NAME", "cs3-nca-employee-passwords")
INSTANCE_TYPE = os.getenv("EC2_INSTANCE_TYPE", "t3.micro")
SUBNET_ID = os.getenv("EC2_SUBNET_ID")
SECURITY_GROUP_ID = os.getenv("EC2_SECURITY_GROUP_ID")
AMI_SSM_PARAMETER = os.getenv(
    "AMI_SSM_PARAMETER",
    "ami-0852a4ffb1d7b687f",  # Windows Server 2022 AMI
)
INSTANCE_PROFILE_PREFIX = os.getenv("INSTANCE_PROFILE_PREFIX", "employee-profile")
MANAGED_POLICY_ARN = os.getenv(
    "IAM_MANAGED_POLICY_ARN", "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
)
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")
WS_DIRECTORY_ID = os.getenv("WORKSPACES_DIRECTORY_ID")
WS_BUNDLE_ID = os.getenv("WORKSPACES_BUNDLE_ID")
WS_SUBNET_IDS = os.getenv("WORKSPACES_SUBNET_IDS", "")

# AD via SSM
AD_USER_OU = os.getenv("AD_USER_OU")
AD_USER_DOMAIN = os.getenv("AD_USER_DOMAIN")
MANAGEMENT_INSTANCE_ID = os.getenv("MANAGEMENT_INSTANCE_ID")
AD_DEFAULT_PASSWORD = os.getenv("AD_DEFAULT_PASSWORD")  # optional fallback
AD_ADMIN_UPN = os.getenv("AD_ADMIN_UPN")
AD_ADMIN_PASSWORD = os.getenv("AD_ADMIN_PASSWORD")
# Optional bind creds (fallback)
AD_BIND_DN = os.getenv("AD_BIND_DN")
AD_BIND_PASSWORD = os.getenv("AD_BIND_PASSWORD")
AD_DOMAIN_NETBIOS = os.getenv("AD_DOMAIN_NETBIOS")
# Optional LDAP endpoint override (e.g. ldaps://domaincontroller:636)
AD_LDAP_URL = os.getenv("AD_LDAP_URL", "")
if not AD_DOMAIN_NETBIOS and AD_USER_DOMAIN:
    AD_DOMAIN_NETBIOS = AD_USER_DOMAIN.split(".")[0].upper()

# Standaard wachtwoord voor nieuwe accounts; kan worden overschreven via env
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD") or AD_DEFAULT_PASSWORD or "Welkom99!!"

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)
password_table = dynamodb.Table(PASSWORD_TABLE_NAME) if PASSWORD_TABLE_NAME else None

iam = boto3.client("iam", region_name=AWS_REGION)
ssm = boto3.client("ssm", region_name=AWS_REGION)
ec2 = boto3.client("ec2", region_name=AWS_REGION)
sns = boto3.client("sns", region_name=AWS_REGION)
workspaces = boto3.client("workspaces", region_name=AWS_REGION)
ds_client = boto3.client("ds", region_name=AWS_REGION)


def generate_password(length: int = 12) -> str:
    # Gebruik een vast startwachtwoord zodat iedereen bij eerste login moet wijzigen
    return DEFAULT_PASSWORD


def update_dynamodb_status(employee_id: str, status: str, extra: dict | None = None):
    print(f"[JOB] Updating DynamoDB status -> {status}")
    update_expression = "SET #s = :s"
    expr_names = {"#s": "status"}
    expr_values = {":s": status}
    if extra:
        for key, val in extra.items():
            expr_key = f"#{key}"
            placeholder = f":{key}"
            expr_names[expr_key] = key
            update_expression += f", {expr_key} = {placeholder}"
            expr_values[placeholder] = val
    table.update_item(
        Key={"employeeId": employee_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def store_employee_password(employee_id: str, email: str, password: str):
    if not password_table:
        print("[JOB] Password table not configured; skipping store")
        return
    item = {
        "employeeId": employee_id,
        "password": password,
        "updatedAt": int(time.time()),
    }
    if email:
        item["email"] = email
    password_table.put_item(Item=item)


def resolve_ami_id() -> str:
    resp = ssm.get_parameter(Name=AMI_SSM_PARAMETER)
    return resp["Parameter"]["Value"]


def ensure_instance_role(employee_id: str) -> Tuple[str, str, str]:
    role_name = f"employee-{employee_id}"
    profile_name = f"{INSTANCE_PROFILE_PREFIX}-{employee_id[:8]}"
    assume_role_doc: Dict[str, Dict] = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_doc),
            Description=f"Per-employee role for {employee_id}",
        )
        print(f"[JOB] Created IAM role {role_name}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"[JOB] IAM role {role_name} already exists")
    # Forceer dat AmazonSSMManagedInstanceCore altijd wordt geattached
    try:
        iam.attach_role_policy(RoleName=role_name, PolicyArn=MANAGED_POLICY_ARN)
        print(f"[JOB] Attached AmazonSSMManagedInstanceCore to {role_name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        print(f"[JOB] Managed policy already attached to {role_name}")
    # Zorg dat het instance profile directory-service permissies heeft voor domain join
    if not WS_DIRECTORY_ID:
        raise Exception("[JOB] WORKSPACES_DIRECTORY_ID ontbreekt; kan domain join policy niet configureren")
    ds_resource = f"arn:aws:ds:{AWS_REGION}:{AWS_ACCOUNT_ID}:directory/{WS_DIRECTORY_ID}"
    inline_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["ds:CreateComputer", "ds:DescribeDirectories"],
                "Resource": ds_resource,
            }
        ],
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="allow-directory-service",
        PolicyDocument=json.dumps(inline_policy_doc),
    )
    try:
        iam.create_instance_profile(InstanceProfileName=profile_name)
        print(f"[JOB] Created instance profile {profile_name}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"[JOB] Instance profile {profile_name} already exists")
    try:
        iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name, RoleName=role_name
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"LimitExceeded", "EntityAlreadyExists"}:
            raise
        print(f"[JOB] Role {role_name} already in profile {profile_name}")
    role = iam.get_role(RoleName=role_name)
    profile = iam.get_instance_profile(InstanceProfileName=profile_name)
    time.sleep(5)
    return role["Role"]["Arn"], profile_name, profile["InstanceProfile"]["Arn"]


def launch_instance(employee_id: str, profile_name: str, profile_arn: str, ami_id: str) -> str:
    if not SUBNET_ID:
        raise ValueError("EC2_SUBNET_ID is required to start the instance")
    params: Dict[str, object] = {
        "ImageId": ami_id,
        "InstanceType": INSTANCE_TYPE,
        "MinCount": 1,
        "MaxCount": 1,
        "SubnetId": SUBNET_ID,
        "IamInstanceProfile": {"Arn": profile_arn},
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"employee-{employee_id}"},
                    {"Key": "employeeId", "Value": employee_id},
                    {"Key": "Project", "Value": "cs3-nca"},
                ],
            }
        ],
        "UserData": f"""#!/bin/bash
echo "employeeId={employee_id}" >> /etc/employee-meta
""",
    }
    if SECURITY_GROUP_ID:
        params["SecurityGroupIds"] = [SECURITY_GROUP_ID]
    last_exc = None
    for attempt in range(3):
        try:
            resp = ec2.run_instances(**params)
            instance_id = resp["Instances"][0]["InstanceId"]
            print(f"[JOB] EC2 instance started: {instance_id}")
            return instance_id
        except ClientError as exc:
            last_exc = exc
            if exc.response["Error"]["Code"] == "InvalidParameterValue":
                time.sleep(5)
                continue
            raise
    raise last_exc


def create_workspace(employee_id: str, email: str) -> dict:
    if not WS_DIRECTORY_ID or not WS_BUNDLE_ID:
        print("[JOB] WorkSpaces config missing, skipping workspace provisioning")
        return {}
    user_name = email.split("@")[0] if email else f"user-{employee_id}"

    def get_registration_code() -> str | None:
        try:
            resp = workspaces.describe_workspace_directories(DirectoryIds=[WS_DIRECTORY_ID])
            dirs = resp.get("Directories", [])
            if dirs:
                return dirs[0].get("RegistrationCode")
        except Exception as exc:
            print(f"[JOB] Failed to fetch registration code: {exc}")
        return None

    resp = workspaces.create_workspaces(
        Workspaces=[
            {
                "DirectoryId": WS_DIRECTORY_ID,
                "UserName": user_name,
                "BundleId": WS_BUNDLE_ID,
                "WorkspaceProperties": {"RunningMode": "AUTO_STOP"},
                "Tags": [
                    {"Key": "employeeId", "Value": employee_id},
                    {"Key": "Project", "Value": "cs3-nca"},
                ],
            }
        ]
    )

    pending = resp.get("PendingRequests", [])
    failed = resp.get("FailedRequests", [])
    if failed:
        fail = failed[0]
        reason = fail.get("ErrorMessage") or fail.get("ErrorCode") or "unknown failure"
        raise RuntimeError(f"WorkSpaces request failed: {reason}")
    if not pending:
        raise RuntimeError("WorkSpaces API returned no pending requests")
    ws_info = pending[0]
    ws_id = ws_info.get("WorkspaceId")
    print(f"[JOB] WorkSpace requested: {ws_id}")
    for _ in range(10):
        desc = workspaces.describe_workspaces(WorkspaceIds=[ws_id])
        state = desc["Workspaces"][0]["State"]
        print(f"[JOB] WorkSpace {ws_id} state: {state}")
        if state == "AVAILABLE":
            break
        if state in {"ERROR", "FAILED"}:
            raise RuntimeError(f"WorkSpace {ws_id} failed with state {state}")
        time.sleep(6)
    reg_code = get_registration_code()
    return {"workspaceId": ws_id, "workspaceState": state, "registrationCode": reg_code}


def publish_sns(payload: dict):
    if not SNS_TOPIC_ARN:
        return
    try:
        reg_code = payload.get("registrationCode")
        username = payload.get("username")
        pwd = payload.get("password")
        ws_id = payload.get("workspaceId")
        lines = [
            "Nieuwe medewerker is voorzien:",
            f"- EmployeeId: {payload.get('employeeId')}",
            f"- WorkspaceId: {ws_id}",
            f"- WorkspaceState: {payload.get('workspaceState')}",
            f"- EC2: {payload.get('ec2InstanceId')}",
            f"- IAM Role: {payload.get('roleArn')}",
        ]
        if reg_code:
            lines.append(f"- WorkSpaces registration code: {reg_code}")
        if username:
            lines.append(f"- Username: {username}")
        if pwd:
            lines.append(f"- Password: {pwd}")
        lines.append("")
        lines.append("Download client: https://clients.amazonworkspaces.com/")
        if reg_code:
            lines.append("Gebruik de registration code in de client om in te loggen.")
        message_text = "\n".join(lines)
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject="New employee provisioned", Message=message_text)
        print("[JOB] SNS notification sent")
    except Exception as exc:
        print(f"[JOB] SNS publish failed: {exc}")


def publish_delete_sns(payload: dict, errors: list[str] | None = None):
    if not SNS_TOPIC_ARN:
        return
    try:
        lines = [
            "Medewerker verwijderd:",
            f"- EmployeeId: {payload.get('employeeId')}",
            f"- Email: {payload.get('email')}",
            f"- Department: {payload.get('department')}",
            f"- WorkspaceId: {payload.get('workspaceId') or 'n.v.t.'}",
        ]
        if errors:
            lines.append("")
            lines.append("Let op: sommige resources konden niet worden verwijderd:")
            for err in errors:
                lines.append(f"- {err}")
            subject = "Employee delete afgerond met waarschuwingen"
        else:
            subject = "Employee delete afgerond"
        message_text = "\n".join(lines)
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message_text)
        print("[JOB] SNS deletion notification sent")
    except Exception as exc:
        print(f"[JOB] SNS delete publish failed: {exc}")


def create_or_update_ad_user_via_ssm(username: str, password: str, email: str, name: str, department: str):
    if not (MANAGEMENT_INSTANCE_ID and AD_USER_OU and AD_USER_DOMAIN):
        print("[JOB] AD via SSM not configured; skipping AD user creation")
        return
    display_name = name or username
    mail_attr = email
    ou_path = AD_USER_OU
    upn = f"{username}@{AD_USER_DOMAIN}"
    admin_upn = AD_ADMIN_UPN or AD_BIND_DN or ""
    admin_pwd = AD_ADMIN_PASSWORD or AD_BIND_PASSWORD or AD_DEFAULT_PASSWORD or ""
    if not admin_upn or not admin_pwd:
        raise Exception("[JOB] AD admin credentials ontbreken (AD_ADMIN_UPN/AD_ADMIN_PASSWORD)")
    dept = department or "General"
    group_name = f"Dept-{dept.replace(' ', '_')}"
    ps_script = f"""
$ErrorActionPreference = "Stop"
if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {{
    try {{
        Install-WindowsFeature RSAT-AD-PowerShell -IncludeAllSubFeature -IncludeManagementTools | Out-Null
    }} catch {{
        Write-Host "RSAT install failed: $_"
    }}
}}
Import-Module ActiveDirectory
$User = "{username}"
$Pass = ConvertTo-SecureString "{password}" -AsPlainText -Force
$Ou = "{ou_path}"
$Upn = "{upn}"
$DisplayName = "{display_name}"
$Mail = "{mail_attr}"
$Dept = "{dept}"
$GroupName = "{group_name}"
$AdminUser = '{admin_upn}'
$AdminPass = ConvertTo-SecureString '{admin_pwd}' -AsPlainText -Force
$Cred = New-Object System.Management.Automation.PSCredential ($AdminUser, $AdminPass)

$existing = Get-ADUser -Filter "sAMAccountName -eq '$User'" -ErrorAction SilentlyContinue
if ($existing) {{
    Set-ADAccountPassword -Identity $User -NewPassword $Pass -Reset -Credential $Cred
    Enable-ADAccount -Identity $User -Credential $Cred
    Set-ADUser -Identity $User -EmailAddress $Mail -DisplayName $DisplayName -UserPrincipalName $Upn -Department $Dept -ChangePasswordAtLogon $false -Credential $Cred
}} else {{
    New-ADUser `
      -Name $DisplayName `
      -SamAccountName $User `
      -UserPrincipalName $Upn `
      -EmailAddress $Mail `
      -Path $Ou `
      -AccountPassword $Pass `
      -Enabled $true `
    -Department $Dept `
    -Credential $Cred
}}

Set-ADUser -Identity $User -ChangePasswordAtLogon $false -Credential $Cred

# Maak of hergebruik een groep per department en koppel de user
$grp = Get-ADGroup -Filter "Name -eq '$GroupName'" -ErrorAction SilentlyContinue
if (-not $grp) {{
    $grp = New-ADGroup -Name $GroupName -SamAccountName $GroupName -GroupScope Global -Path $Ou -Credential $Cred -Description "RBAC group for $Dept"
}}
try {{
    Add-ADGroupMember -Identity $GroupName -Members $User -Credential $Cred -ErrorAction SilentlyContinue
}} catch {{
    Write-Host "Add-ADGroupMember failed: $_"
}}
"""
    try:
        resp = ssm.send_command(
            InstanceIds=[MANAGEMENT_INSTANCE_ID],
            DocumentName="AWS-RunPowerShellScript",
            Parameters={"commands": [ps_script]},
        )
        cmd_id = resp['Command']['CommandId']
        print(f"[JOB] SSM AD create/update sent for user {username}: {cmd_id}")
        # wacht op voltooiing en fail als er auth/AD errors staan in stdout/stderr
        for _ in range(30):
            time.sleep(5)
            info = ssm.list_command_invocations(CommandId=cmd_id, Details=True)
            inv = info.get("CommandInvocations", [])
            if not inv:
                continue
            status = inv[0].get("Status")
            stdout = inv[0].get("StandardOutputContent") or ""
            stderr = inv[0].get("StandardErrorContent") or ""
            combined = (stdout + "\n" + stderr).strip()
            if status in ("Success", "Failed", "Cancelled", "TimedOut"):
                if status != "Success" or "AuthenticationException" in combined or "rejected the client credentials" in combined:
                    err = combined or inv[0].get("StatusDetails") or "Onbekende fout"
                    raise Exception(f"[JOB] AD SSM create/update mislukt: {err}")
                break
        else:
            raise Exception(f"[JOB] AD SSM create/update timeout voor {cmd_id}")
    except Exception as exc:
        print(f"[JOB] Failed to create/update AD user via SSM (continuing): {exc}")


def set_ad_password_via_ssm(username: str, password: str):
    if not MANAGEMENT_INSTANCE_ID:
        print("[JOB] SSM password reset not configured; skipping AD password set")
        return
    admin_upn = AD_ADMIN_UPN or AD_BIND_DN or ""
    admin_pwd = AD_ADMIN_PASSWORD or AD_BIND_PASSWORD or AD_DEFAULT_PASSWORD or ""
    ps_script = f"""
$ErrorActionPreference = "Stop"
if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {{
    try {{
        Install-WindowsFeature RSAT-AD-PowerShell -IncludeAllSubFeature -IncludeManagementTools | Out-Null
    }} catch {{
        Write-Host "RSAT install failed: $_"
    }}
}}
Import-Module ActiveDirectory
$User = "{username}"
$SecurePass = ConvertTo-SecureString "{password}" -AsPlainText -Force
$AdminUser = "{admin_upn}"
$AdminPass = ConvertTo-SecureString "{admin_pwd}" -AsPlainText -Force
$Cred = New-Object System.Management.Automation.PSCredential ($AdminUser, $AdminPass)
Set-ADAccountPassword -Identity $User -NewPassword $SecurePass -Reset -Credential $Cred
Enable-ADAccount -Identity $User -Credential $Cred
Set-ADUser -Identity $User -ChangePasswordAtLogon $false -Credential $Cred
"""
    try:
        resp = ssm.send_command(
            InstanceIds=[MANAGEMENT_INSTANCE_ID],
            DocumentName="AWS-RunPowerShellScript",
            Parameters={"commands": [ps_script]},
        )
        print(f"[JOB] SSM password reset sent for user {username}: {resp['Command']['CommandId']}")
    except Exception as exc:
        print(f"[JOB] Failed to set AD password via SSM (continuing): {exc}")


def delete_ad_user_via_ssm(username: str):
    if not (MANAGEMENT_INSTANCE_ID and AD_USER_DOMAIN):
        print("[JOB] AD via SSM not configured; skipping AD deletion")
        return
    admin_upn = AD_ADMIN_UPN or AD_BIND_DN or ""
    admin_pwd = AD_ADMIN_PASSWORD or AD_BIND_PASSWORD or AD_DEFAULT_PASSWORD or ""
    ps_script = f"""
$ErrorActionPreference = "Stop"
Import-Module ActiveDirectory
$User = "{username}"
$AdminUser = '{admin_upn}'
$AdminPass = ConvertTo-SecureString '{admin_pwd}' -AsPlainText -Force
$Cred = New-Object System.Management.Automation.PSCredential ($AdminUser, $AdminPass)
$existing = Get-ADUser -Filter "sAMAccountName -eq '$User'" -ErrorAction SilentlyContinue
if ($existing) {{
    try {{
        Remove-ADUser -Identity $User -Confirm:$false -Credential $Cred
    }} catch {{
        Write-Host "Remove-ADUser failed: $_"
    }}
}}
"""
    try:
        resp = ssm.send_command(
            InstanceIds=[MANAGEMENT_INSTANCE_ID],
            DocumentName="AWS-RunPowerShellScript",
            Parameters={"commands": [ps_script]},
        )
        print(f"[JOB] SSM AD delete sent for user {username}: {resp['Command']['CommandId']}")
    except Exception as exc:
        print(f"[JOB] Failed to delete AD user via SSM (continuing): {exc}")


def main():
    employee_id = os.getenv("EMPLOYEE_ID")
    if not employee_id:
        raise ValueError("EMPLOYEE_ID environment variable is required")
    name = os.getenv("NAME", "unknown")
    email = os.getenv("EMAIL", "")
    department = os.getenv("DEPARTMENT", "")
    action = os.getenv("ACTION", "onboard") or "onboard"

    try:
        if action == "delete":
            print(f"[JOB] Starting deletion job for {employee_id}")
            errors: list[str] = []
            # mark status and attempt cleanup
            update_dynamodb_status(employee_id, "DELETING")

            # load existing item from DynamoDB to find workspaceId / email
            resp = table.get_item(Key={"employeeId": employee_id})
            item = resp.get("Item", {})

            username = os.getenv("EMAIL") or item.get("email", "")
            ws_id = item.get("workspaceId") or os.getenv("WORKSPACE_ID")
            department = os.getenv("DEPARTMENT") or item.get("department")

            # delete AD user via SSM if configured and we have username
            if username and MANAGEMENT_INSTANCE_ID:
                try:
                    user = username.split("@")[0]
                    delete_ad_user_via_ssm(user)
                except Exception as exc:
                    errors.append(f"AD deletion failed: {exc}")

            # terminate workspace if present
            if ws_id:
                try:
                    print(f"[JOB] Terminating WorkSpace {ws_id}")
                    workspaces.terminate_workspaces(TerminateWorkspaceRequests=[{"WorkspaceId": ws_id}])
                except Exception as exc:
                    errors.append(f"WorkSpaces termination error: {exc}")

            # terminate any EC2 instances with tag employeeId
            try:
                instances = ec2.describe_instances(Filters=[{"Name": "tag:employeeId", "Values": [employee_id]}])
                to_terminate = []
                for r in instances.get("Reservations", []):
                    for i in r.get("Instances", []):
                        iid = i.get("InstanceId")
                        state = i.get("State", {}).get("Name")
                        if state and state.lower() not in {"shutting-down", "terminated"}:
                            to_terminate.append(iid)
                if to_terminate:
                    print(f"[JOB] Terminating EC2 instances: {to_terminate}")
                    ec2.terminate_instances(InstanceIds=to_terminate)
            except Exception as exc:
                errors.append(f"EC2 termination error: {exc}")

            # remove IAM role and instance profile
            try:
                role_name = f"employee-{employee_id}"
                profile_name = f"{INSTANCE_PROFILE_PREFIX}-{employee_id[:8]}"
                # remove role from instance profile if exists
                try:
                    profile = iam.get_instance_profile(InstanceProfileName=profile_name)
                    for role in profile.get("InstanceProfile", {}).get("Roles", []):
                        try:
                            iam.remove_role_from_instance_profile(InstanceProfileName=profile_name, RoleName=role.get("RoleName"))
                        except Exception:
                            pass
                    try:
                        iam.delete_instance_profile(InstanceProfileName=profile_name)
                    except Exception:
                        pass
                except iam.exceptions.NoSuchEntityException:
                    pass

                # detach managed policies and delete role
                try:
                    attached = iam.list_attached_role_policies(RoleName=role_name)
                    for pol in attached.get("AttachedPolicies", []):
                        try:
                            iam.detach_role_policy(RoleName=role_name, PolicyArn=pol.get("PolicyArn"))
                        except Exception:
                            pass
                    # delete inline policies
                    try:
                        inlines = iam.list_role_policies(RoleName=role_name)
                        for name in inlines.get("PolicyNames", []):
                            try:
                                iam.delete_role_policy(RoleName=role_name, PolicyName=name)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        iam.delete_role(RoleName=role_name)
                    except Exception as exc:
                        errors.append(f"IAM role delete error: {exc}")
                except iam.exceptions.NoSuchEntityException:
                    pass
            except Exception as exc:
                errors.append(f"IAM cleanup error: {exc}")

            if errors:
                print(f"[JOB] Cleanup did not finish cleanly: {'; '.join(errors)}")
                update_dynamodb_status(
                    employee_id,
                    "DELETE_FAILED",
                    {"error": "; ".join(errors), "updatedAt": int(time.time())},
                )
                publish_delete_sns(
                    {
                        "employeeId": employee_id,
                        "email": username,
                        "department": department,
                        "workspaceId": ws_id,
                    },
                    errors=errors,
                )
                return

            # finally remove record from DynamoDB
            try:
                table.delete_item(Key={"employeeId": employee_id})
                print(f"[JOB] Deleted DynamoDB record for {employee_id}")
            except Exception as exc:
                errors.append(f"DynamoDB delete error: {exc}")

            if errors:
                update_dynamodb_status(
                    employee_id,
                    "DELETE_FAILED",
                    {"error": "; ".join(errors), "updatedAt": int(time.time())},
                )
                publish_delete_sns(
                    {
                        "employeeId": employee_id,
                        "email": username,
                        "department": department,
                        "workspaceId": ws_id,
                    },
                    errors=errors,
                )
                return

            publish_delete_sns(
                {
                    "employeeId": employee_id,
                    "email": username,
                    "department": department,
                    "workspaceId": ws_id,
                }
            )
            print(f"[JOB] Deletion complete for {employee_id}")
            return

        update_dynamodb_status(employee_id, "PROVISIONING")
        # EC2 provisioning overbodig voor dit scenario
        role_arn = None
        profile_name = None
        instance_id = None
        update_dynamodb_status(
            employee_id,
            "ACTIVE",
            {
                "name": name,
                "email": email,
                "department": department,
                "updatedAt": int(time.time()),
            },
        )
        # AD user provisioning via SSM + random password
        username = email.split("@")[0] if email else None
        user_password = generate_password()
        if username and MANAGEMENT_INSTANCE_ID:
            try:
                create_or_update_ad_user_via_ssm(
                    username=username,
                    password=user_password,
                    email=email,
                    name=name,
                    department=department,
                )
                # wacht kort zodat AD replicatie klaar is
                time.sleep(5)
            except Exception as ssm_exc:
                print(f"[JOB] AD password via SSM failed (continuing): {ssm_exc}")
        # EC2 provisioning in plaats van WorkSpaces
        ec2_result = create_ec2_for_employee(employee_id, email, department)
        if ec2_result:
            update_dynamodb_status(
                employee_id,
                "ACTIVE",
                {
                    "instanceId": ec2_result.get("instance_id"),
                    "name": name,
                    "email": email,
                    "department": department,
                    "rdp_file": ec2_result.get("rdp_file"),
                },
            )
        # Stuur SNS met EC2/RDP info
        subject = f"Nieuwe EC2 voor medewerker: {ec2_result.get('user_name')}"
        message = (
            f"Nieuwe EC2 instance is aangemaakt voor {ec2_result.get('user_name')}\n"
            f"InstanceId: {ec2_result.get('instance_id')}\n"
            f"RDP-bestand: {ec2_result.get('rdp_file')}\n"
            f"Gebruikersnaam: {ec2_result.get('user_name')}\n"
            f"Wachtwoord: {ec2_result.get('password')}\n"
            f"Domein: {AD_USER_DOMAIN}\n"
        )
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
        print(f"[JOB] Onboarding complete for {employee_id}")
    except Exception as exc:
        print(f"[JOB] Failed onboarding for {employee_id}: {exc}")
        update_dynamodb_status(
            employee_id,
            "FAILED",
            {"error": str(exc), "updatedAt": int(time.time())},
        )
        raise


if __name__ == "__main__":
    main()
