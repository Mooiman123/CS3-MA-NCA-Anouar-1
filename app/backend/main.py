import os
import json
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import boto3
from fastapi.middleware.cors import CORSMiddleware

from utils.dynamodb import (
    create_employee,
    get_employee,
    list_employees,
    update_employee,
    delete_employee,
    find_employee_by_email,
    get_employee_password,
    find_password_by_email,
)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CS3 NCA Employee API")

allowed_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
origins = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]

# Allow the frontend load balancer to call the backend API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EVENT_SOURCE = "eks.backend"
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
ALLOWED_EMAILS = [e.strip().lower() for e in os.getenv("PORTAL_ALLOWED_EMAILS", "hr@innovatech.com").split(",") if e.strip()]

eventbridge = boto3.client("events", region_name=AWS_REGION)


class EmployeeCreateRequest(BaseModel):
    name: str
    email: EmailStr
    department: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(payload: LoginRequest):
    email_lower = payload.email.lower()
    if ALLOWED_EMAILS and email_lower not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Geen toegang")
    emp = find_employee_by_email(payload.email)
    if not emp:
        raise HTTPException(status_code=401, detail="Login mislukt")
    pwd_record = get_employee_password(emp["employeeId"]) or find_password_by_email(payload.email)
    if not pwd_record or pwd_record.get("password") != payload.password:
        raise HTTPException(status_code=401, detail="Login mislukt")
    name = emp.get("name") or payload.email.split("@")[0]
    return {"email": payload.email, "name": name}


@app.post("/employees")
def create_employee_endpoint(payload: EmployeeCreateRequest):
    employee_id = create_employee(payload.dict())

    # stuur event naar EventBridge
    detail = {
        "employeeId": employee_id,
        "email": payload.email,
        "name": payload.name,
        "department": payload.department,
    }

    eventbridge.put_events(
        Entries=[
            {
                "Source": EVENT_SOURCE,
                "DetailType": "employeeCreated",
                "Detail": json.dumps(detail),
            }
        ]
    )

    return {"employeeId": employee_id, "status": "CREATED"}


@app.get("/employees/{employee_id}")
def get_employee_endpoint(employee_id: str):
    item = get_employee(employee_id)
    if not item:
        raise HTTPException(status_code=404, detail="Employee not found")
    return item


@app.get("/employees")
def list_employees_endpoint():
    return list_employees()


@app.put("/employees/{employee_id}")
def update_employee_endpoint(employee_id: str, payload: EmployeeCreateRequest):
    item = get_employee(employee_id)
    if not item:
        raise HTTPException(status_code=404, detail="Employee not found")

    updated = update_employee(
        employee_id,
        {
            "name": payload.name,
            "email": payload.email,
            "department": payload.department,
        },
    )
    return updated


@app.delete("/employees/{employee_id}")
def delete_employee_endpoint(employee_id: str):
    item = get_employee(employee_id)
    if not item:
        raise HTTPException(status_code=404, detail="Employee not found")
    # mark the record as DELETING and emit an event so worker jobs can clean up
    update_employee(employee_id, {"status": "DELETING"})
    logger.info(f"[DELETE] Employee {employee_id} marked as DELETING")

    detail = {
        "employeeId": employee_id,
        "email": item.get("email"),
        "name": item.get("name"),
        "department": item.get("department"),
        "workspaceId": item.get("workspaceId"),
        "action": "delete",
    }

    try:
        response = eventbridge.put_events(
            Entries=[
                {
                    "Source": EVENT_SOURCE,
                    "DetailType": "employeeDeleted",
                    "Detail": json.dumps(detail),
                }
            ]
        )
        logger.info(f"[DELETE] EventBridge response: {response}")
    except Exception as e:
        logger.error(f"[DELETE] EventBridge error: {e}")
        raise HTTPException(status_code=500, detail=f"EventBridge error: {e}")

    return {"deleted": True, "employeeId": employee_id, "status": "DELETING"}
