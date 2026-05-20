from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.votenow_common import (
    InviteListRequest,
    NotificationChannel,
    Respondent,
    VerificationMethod,
    VoteRole,
    build_audit_event,
    has_permission,
)
from shared.votenow_common.settings import Settings

settings = Settings(service_name="verification-service", service_port=8503)
app = FastAPI(title="VoteNow Verification Service", version="1.0.0")

invite_registry: dict[str, set[str]] = {"SURVEY-DEMO": {"student-001", "student-002", "student-003"}}
pending_codes: dict[str, dict[str, Any]] = {}
confirmed_tokens: set[str] = set()
duplicate_keys: set[str] = set()
audit_log: list[dict[str, Any]] = []


class VerificationCodeRequest(BaseModel):
    survey_id: str
    respondent_id: str | None = None
    email: str | None = None
    phone: str | None = None
    method: VerificationMethod
    actor_id: str
    actor_role: VoteRole


class VerificationCodeConfirmRequest(BaseModel):
    verification_id: str
    code: str


class ValidateVoterRequest(BaseModel):
    survey_id: str
    respondent: Respondent
    invited_only: bool
    verification_method: VerificationMethod
    verification_code: str | None = None


class DuplicateCheckRequest(BaseModel):
    duplicate_key: str


class DuplicateRegisterRequest(BaseModel):
    duplicate_key: str


VerificationCodeRequest.model_rebuild()
VerificationCodeConfirmRequest.model_rebuild()
ValidateVoterRequest.model_rebuild()
DuplicateCheckRequest.model_rebuild()
DuplicateRegisterRequest.model_rebuild()


def _assert_permission(role: VoteRole, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(
    actor_id: str,
    actor_role: VoteRole,
    action: str,
    object_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type="verification",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _respondent_key(respondent: Respondent) -> str:
    return (respondent.respondent_id or respondent.email or respondent.phone or respondent.ip_address).strip().lower()


async def _notify_code(destination: str, method: VerificationMethod, code: str, survey_id: str) -> None:
    if method not in {VerificationMethod.EMAIL, VerificationMethod.SMS}:
        return
    channel = NotificationChannel.EMAIL if method == VerificationMethod.EMAIL else NotificationChannel.SMS
    payload = {
        "channel": channel.value,
        "recipient": destination,
        "subject": f"VoteNow verification for {survey_id}",
        "body": f"Your confirmation code: {code}",
        "metadata": {"survey_id": survey_id, "kind": "verification"},
        "actor_role": VoteRole.ADMIN.value,
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(f"{settings.notification_service_url}/notify/send", json=payload)
        except httpx.HTTPError:
            pass


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/verification/invites")
async def upsert_invites(request: InviteListRequest, actor_id: str, actor_role: VoteRole) -> dict[str, Any]:
    _assert_permission(actor_role, "verification:manage")
    invite_registry[request.survey_id] = {item.strip().lower() for item in request.allowed_ids if item.strip()}
    _audit(actor_id, actor_role, "verification.invites.upsert", request.survey_id, {"count": len(request.allowed_ids)})
    return {"survey_id": request.survey_id, "allowed_count": len(invite_registry[request.survey_id])}


@app.post("/verification/request-code")
async def request_code(request: VerificationCodeRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "verification:manage")
    if request.method not in {VerificationMethod.EMAIL, VerificationMethod.SMS}:
        raise HTTPException(status_code=400, detail="Code delivery is supported only for email or sms")

    destination = request.email if request.method == VerificationMethod.EMAIL else request.phone
    if not destination:
        raise HTTPException(status_code=400, detail="Missing destination for selected verification method")

    verification_id = str(uuid4())
    code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    pending_codes[verification_id] = {
        "survey_id": request.survey_id,
        "code": code,
        "destination": destination.strip().lower(),
        "expires_at": expires_at,
    }
    await _notify_code(destination, request.method, code, request.survey_id)
    _audit(request.actor_id, request.actor_role, "verification.code.request", verification_id)
    return {
        "verification_id": verification_id,
        "expires_at": expires_at.isoformat(),
        "code_preview": code,
    }


@app.post("/verification/confirm-code")
async def confirm_code(request: VerificationCodeConfirmRequest) -> dict[str, Any]:
    payload = pending_codes.get(request.verification_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Verification session not found")
    if payload["expires_at"] < datetime.now(UTC):
        pending_codes.pop(request.verification_id, None)
        raise HTTPException(status_code=410, detail="Verification code expired")
    if payload["code"] != request.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    token = f"{payload['survey_id']}:{payload['destination']}:{payload['code']}"
    confirmed_tokens.add(token)
    pending_codes.pop(request.verification_id, None)
    return {"status": "confirmed", "token": token}


@app.post("/verification/validate-voter")
async def validate_voter(request: ValidateVoterRequest) -> dict[str, Any]:
    respondent_key = _respondent_key(request.respondent)

    if request.invited_only:
        allowed = invite_registry.get(request.survey_id, set())
        if respondent_key not in allowed:
            raise HTTPException(status_code=403, detail="Respondent is not in invited list")

    if request.verification_method in {VerificationMethod.EMAIL, VerificationMethod.SMS}:
        if not request.verification_code:
            raise HTTPException(status_code=400, detail="Verification code is required")

        destination = (request.respondent.email or request.respondent.phone or "").strip().lower()
        token = f"{request.survey_id}:{destination}:{request.verification_code}"
        if token not in confirmed_tokens:
            raise HTTPException(status_code=403, detail="Respondent verification is not confirmed")

    return {"status": "ok", "respondent_key": respondent_key}


@app.post("/verification/check-duplicate")
async def check_duplicate(request: DuplicateCheckRequest) -> dict[str, Any]:
    if request.duplicate_key in duplicate_keys:
        raise HTTPException(status_code=409, detail="Duplicate vote detected")
    return {"status": "ok"}


@app.post("/verification/register-duplicate")
async def register_duplicate(request: DuplicateRegisterRequest) -> dict[str, Any]:
    duplicate_keys.add(request.duplicate_key)
    return {"status": "registered", "duplicate_count": len(duplicate_keys)}


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: VoteRole = VoteRole.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:]}
