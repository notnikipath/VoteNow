from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.votenow_common import (
    ResponseSubmitRequest,
    Settings,
    Survey,
    VoteRole,
    check_captcha,
    duplicate_fingerprint,
    has_permission,
    is_ip_rate_limited,
    register_ip_submission,
    sign_token,
    verify_token,
)


class GatewaySettings(BaseSettings):
    service_name: str = "api-gateway"
    service_port: int = 8500

    survey_service_url: str = Settings().survey_service_url
    response_service_url: str = Settings().response_service_url
    verification_service_url: str = Settings().verification_service_url
    analytics_service_url: str = Settings().analytics_service_url
    export_service_url: str = Settings().export_service_url
    notification_service_url: str = Settings().notification_service_url

    jwt_secret: str = Settings().jwt_secret
    token_exp_minutes: int = Settings().token_exp_minutes
    captcha_shared_secret: str = Settings().captcha_shared_secret

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = GatewaySettings()
app = FastAPI(title="VoteNow API Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ip_submission_log: dict[str, list[datetime]] = {}


class AuthRequest(BaseModel):
    user_id: str
    role: VoteRole
    language: str = Field(default="ru", pattern="^(ru|en)$")


class PublicSurveySubmitRequest(ResponseSubmitRequest):
    pass


AuthRequest.model_rebuild()
PublicSurveySubmitRequest.model_rebuild()


def _service_urls() -> dict[str, str]:
    return {
        "survey": settings.survey_service_url,
        "response": settings.response_service_url,
        "verification": settings.verification_service_url,
        "analytics": settings.analytics_service_url,
        "export": settings.export_service_url,
        "notification": settings.notification_service_url,
    }


async def _post_json(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def _is_missing_survey_analytics(error: HTTPException) -> bool:
    if error.status_code != 404:
        return False
    return "Survey analytics not found" in str(error.detail)


async def _load_analytics_bundle(client: httpx.AsyncClient, survey_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    live = await _get_json(client, f"{settings.analytics_service_url}/analytics/{survey_id}/live")
    charts = await _get_json(client, f"{settings.analytics_service_url}/analytics/{survey_id}/charts")
    tables = await _get_json(client, f"{settings.analytics_service_url}/analytics/{survey_id}/tables")
    return live, charts, tables


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/auth/token")
async def issue_token(request: AuthRequest) -> dict[str, str]:
    token = sign_token(
        {"sub": request.user_id, "role": request.role.value, "language": request.language},
        settings.jwt_secret,
        exp_minutes=settings.token_exp_minutes,
    )
    return {"access_token": token, "token_type": "Bearer"}


@app.post("/auth/verify")
async def verify_auth(token: str) -> dict[str, Any]:
    payload = verify_token(token, settings.jwt_secret)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@app.get("/services/health")
async def service_health() -> dict[str, Any]:
    statuses: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=8.0) as client:
        for name, base_url in _service_urls().items():
            try:
                statuses[name] = await _get_json(client, f"{base_url}/health")
            except HTTPException as exc:
                statuses[name] = {"status": "error", "detail": exc.detail}
            except httpx.HTTPError as exc:
                statuses[name] = {"status": "error", "detail": str(exc)}
    return statuses


@app.post("/surveys")
async def create_survey(payload: dict[str, Any]) -> dict[str, Any]:
    role = VoteRole(payload.get("creator_role", VoteRole.MODERATOR.value))
    if not has_permission(role, "survey:create"):
        raise HTTPException(status_code=403, detail="Forbidden")
    async with httpx.AsyncClient(timeout=12.0) as client:
        return await _post_json(client, f"{settings.survey_service_url}/surveys", payload)


@app.get("/surveys/public/{public_token}")
async def public_survey(public_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        return await _get_json(client, f"{settings.survey_service_url}/surveys/public/{public_token}")


@app.post("/verification/request-code")
async def request_code(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        return await _post_json(client, f"{settings.verification_service_url}/verification/request-code", payload)


@app.post("/verification/confirm-code")
async def confirm_code(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        return await _post_json(client, f"{settings.verification_service_url}/verification/confirm-code", payload)


@app.post("/workflow/submit-response")
async def submit_response(request: PublicSurveySubmitRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        survey_payload = await _get_json(client, f"{settings.survey_service_url}/surveys/{request.survey_id}")

        survey = Survey.model_validate(survey_payload)
        if not survey.is_active():
            raise HTTPException(status_code=409, detail="Survey is closed")

        if not check_captcha(request.captcha_token, survey.settings.captcha_required, settings.captcha_shared_secret):
            raise HTTPException(status_code=400, detail="Captcha validation failed")

        if is_ip_rate_limited(
            ip_submission_log,
            request.survey_id,
            request.respondent.ip_address,
            survey.settings.ip_limit_per_hour,
        ):
            raise HTTPException(status_code=429, detail="IP submission limit exceeded")

        duplicate_key = duplicate_fingerprint(
            request.survey_id,
            request.respondent.respondent_id,
            request.respondent.email,
            request.respondent.phone,
            request.respondent.ip_address,
        )

        if survey.settings.prevent_duplicates:
            await _post_json(
                client,
                f"{settings.verification_service_url}/verification/check-duplicate",
                {"duplicate_key": duplicate_key},
            )

        await _post_json(
            client,
            f"{settings.verification_service_url}/verification/validate-voter",
            {
                "survey_id": request.survey_id,
                "respondent": request.respondent.model_dump(mode="json"),
                "invited_only": survey.settings.invited_only,
                "verification_method": survey.settings.verification_method.value,
                "verification_code": request.verification_code,
            },
        )

        response = await _post_json(
            client,
            f"{settings.response_service_url}/responses/save",
            {
                "survey": survey.model_dump(mode="json"),
                "answers": [answer.model_dump(mode="json") for answer in request.answers],
                "respondent": request.respondent.model_dump(mode="json"),
            },
        )

        if survey.settings.prevent_duplicates:
            await _post_json(
                client,
                f"{settings.verification_service_url}/verification/register-duplicate",
                {"duplicate_key": duplicate_key},
            )

        await _post_json(
            client,
            f"{settings.analytics_service_url}/analytics/live/update",
            {
                "survey": survey.model_dump(mode="json"),
                "response": response,
            },
        )

    register_ip_submission(ip_submission_log, request.survey_id, request.respondent.ip_address)
    return response


@app.get("/dashboard/public/{public_token}")
async def public_dashboard(public_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        survey = await _get_json(client, f"{settings.survey_service_url}/surveys/public/{public_token}")
        try:
            analytics, charts, tables = await _load_analytics_bundle(client, survey["survey_id"])
        except HTTPException as error:
            if not _is_missing_survey_analytics(error):
                raise
            await _post_json(
                client,
                f"{settings.analytics_service_url}/analytics/ensure-state",
                {"survey": survey},
            )
            analytics, charts, tables = await _load_analytics_bundle(client, survey["survey_id"])
        exports = await _get_json(client, f"{settings.export_service_url}/exports/files")

    return {
        "survey": survey,
        "live": analytics,
        "charts": charts,
        "tables": tables,
        "exports": exports,
    }


@app.post("/exports/{survey_id}/{file_format}")
async def request_export(survey_id: str, file_format: str) -> dict[str, Any]:
    if file_format not in {"excel", "pdf"}:
        raise HTTPException(status_code=400, detail="Unsupported export format")
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _post_json(client, f"{settings.export_service_url}/exports/{survey_id}/{file_format}", {})


@app.get("/exports/tasks/{task_id}")
async def export_task(task_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _get_json(client, f"{settings.export_service_url}/exports/tasks/{task_id}")
