import os
import time
import uuid
import boto3
from boto3.dynamodb.conditions import Attr
from typing import Dict, Any

TABLE_NAME = os.getenv("EMPLOYEE_TABLE_NAME", "cs3-nca-employees")
PASSWORD_TABLE_NAME = os.getenv("EMPLOYEE_PASSWORD_TABLE_NAME", "cs3-nca-employee-passwords")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
password_table = dynamodb.Table(PASSWORD_TABLE_NAME) if PASSWORD_TABLE_NAME else None


def create_employee(data: Dict[str, Any]) -> str:
    employee_id = str(uuid.uuid4())

    item = {
        "employeeId": employee_id,
        "name": data["name"],
        "email": data["email"],
        "department": data["department"],
        "status": "CREATED"
    }

    table.put_item(Item=item)
    return employee_id


def get_employee(employee_id: str) -> Dict[str, Any]:
    res = table.get_item(Key={"employeeId": employee_id})
    return res.get("Item")


def list_employees() -> Dict[str, Any]:
    """
    Simple scan for demo purposes. For larger datasets, use a GSI/query.
    """
    res = table.scan()
    return res.get("Items", [])


def find_employee_by_email(email: str) -> Dict[str, Any] | None:
    """Lookup a single employee record by email."""
    if not email:
        return None
    response = table.scan(FilterExpression=Attr("email").eq(email))
    items = response.get("Items", [])
    return items[0] if items else None


def store_employee_password(employee_id: str, email: str, password: str):
    if not password_table:
        raise RuntimeError("Password table not configured")
    item = {
        "employeeId": employee_id,
        "password": password,
        "updatedAt": int(time.time()),
    }
    if email:
        item["email"] = email
    password_table.put_item(Item=item)


def get_employee_password(employee_id: str) -> Dict[str, Any] | None:
    if not password_table:
        return None
    res = password_table.get_item(Key={"employeeId": employee_id})
    return res.get("Item")


def find_password_by_email(email: str) -> Dict[str, Any] | None:
    if not password_table or not email:
        return None
    response = password_table.scan(FilterExpression=Attr("email").eq(email))
    items = response.get("Items", [])
    return items[0] if items else None


def update_employee(employee_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    expression = []
    expr_values = {}
    expr_names = {}

    for key, value in data.items():
        expr_key = f"#{key}"
        expr_val = f":{key}"
        expr_names[expr_key] = key
        expr_values[expr_val] = value
        expression.append(f"{expr_key} = {expr_val}")

    if not expression:
        return get_employee(employee_id)

    update_expression = "SET " + ", ".join(expression)

    res = table.update_item(
        Key={"employeeId": employee_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )
    return res.get("Attributes", {})


def delete_employee(employee_id: str) -> None:
    table.delete_item(Key={"employeeId": employee_id})
