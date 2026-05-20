from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.votenow_common import (
    Survey,
    SurveyCreateRequest,
    SurveyQuestion,
    SurveySettings,
    SurveyVisibility,
    VerificationMethod,
    VoteRole,
    build_audit_event,
    has_permission,
    survey_length_recommendation,
)
from shared.votenow_common.settings import Settings

settings = Settings(service_name="survey-service", service_port=8501)
app = FastAPI(title="VoteNow Survey Service", version="1.0.0")

surveys: dict[str, Survey] = {}
audit_log: list[dict[str, Any]] = []


class SurveyStateUpdateRequest(BaseModel):
    actor_id: str
    actor_role: VoteRole
    is_archived: bool | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


SurveyStateUpdateRequest.model_rebuild()


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
            object_type="survey",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _ensure_branch_integrity(questions: list[SurveyQuestion]) -> None:
    question_ids = {item.question_id for item in questions}
    for question in questions:
        if not question.next_map:
            continue
        for _, target_question_id in question.next_map.items():
            if target_question_id not in question_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid branching target: {target_question_id} is not a known question",
                )


def _issue_token() -> str:
    return uuid4().hex[:12]


def _public_url(token: str) -> str:
    return f"https://votenow.local/s/{token}"


def _seed_demo_survey() -> Survey:
    now = datetime.now(UTC)
    questions = [
        SurveyQuestion(
            question_id="q1",
            title="What is your primary use case for VoteNow?",
            question_type="single_choice",
            options=["Education", "Community", "Corporate", "Events"],
            next_map={"Corporate": "q2", "Events": "q5"},
        ),
        SurveyQuestion(
            question_id="q2",
            title="Which capabilities do you need most?",
            question_type="multiple_choice",
            options=["Invited voting", "Real-time dashboard", "Export", "Integrations"],
            max_choices=3,
        ),
        SurveyQuestion(
            question_id="q3",
            title="How do you rate survey creation speed?",
            question_type="rating",
            rating_min=1,
            rating_max=10,
            rating_step=1,
        ),
        SurveyQuestion(
            question_id="q4",
            title="Share your feedback in free form",
            question_type="open_text",
            required=False,
        ),
        SurveyQuestion(
            question_id="q5",
            title="Choose the best event format",
            question_type="tournament",
            options=["Workshop", "Panel", "Networking", "Demo show"],
            required=False,
        ),
    ]
    survey = Survey(
        survey_id="SURVEY-DEMO",
        public_token="demo-votenow",
        title="VoteNow Product Feedback",
        description="Demo survey that includes all mandatory question types",
        questions=questions,
        settings=SurveySettings(
            visibility=SurveyVisibility.PUBLIC,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=7),
            allow_anonymous=True,
            prevent_duplicates=True,
            invited_only=False,
            captcha_required=True,
            ip_limit_per_hour=4,
            verification_method=VerificationMethod.NONE,
            show_live_dashboard=True,
        ),
        created_by="demo-admin",
        creator_role=VoteRole.ADMIN,
    )
    return survey


surveys["SURVEY-DEMO"] = _seed_demo_survey()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/surveys")
async def create_survey(request: SurveyCreateRequest) -> dict[str, Any]:
    _assert_permission(request.creator_role, "survey:create")
    _ensure_branch_integrity(request.questions)
    survey = Survey(
        survey_id=f"SURVEY-{uuid4().hex[:8].upper()}",
        public_token=_issue_token(),
        title=request.title,
        description=request.description,
        questions=request.questions,
        settings=request.settings,
        created_by=request.created_by,
        creator_role=request.creator_role,
    )
    surveys[survey.survey_id] = survey
    _audit(request.created_by, request.creator_role, "survey.create", survey.survey_id)
    payload = survey.model_dump(mode="json")
    payload["public_url"] = _public_url(survey.public_token)
    return payload


@app.get("/surveys")
async def list_surveys(
    visibility: SurveyVisibility | None = None,
    active_only: bool = False,
) -> dict[str, Any]:
    items = []
    for survey in surveys.values():
        if visibility and survey.settings.visibility != visibility:
            continue
        if active_only and not survey.is_active():
            continue
        row = survey.model_dump(mode="json")
        row["is_active"] = survey.is_active()
        row["public_url"] = _public_url(survey.public_token)
        items.append(row)
    return {"items": items, "count": len(items)}


@app.get("/surveys/{survey_id}")
async def get_survey(survey_id: str) -> dict[str, Any]:
    survey = surveys.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    payload = survey.model_dump(mode="json")
    payload["is_active"] = survey.is_active()
    payload["public_url"] = _public_url(survey.public_token)
    return payload


@app.get("/surveys/public/{public_token}")
async def get_public_survey(public_token: str) -> dict[str, Any]:
    for survey in surveys.values():
        if survey.public_token != public_token:
            continue
        if survey.settings.visibility == SurveyVisibility.PRIVATE:
            raise HTTPException(status_code=403, detail="Private survey")
        payload = survey.model_dump(mode="json")
        payload["is_active"] = survey.is_active()
        payload["public_url"] = _public_url(survey.public_token)
        return payload
    raise HTTPException(status_code=404, detail="Survey not found")


@app.patch("/surveys/{survey_id}/state")
async def update_state(survey_id: str, request: SurveyStateUpdateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "survey:update")
    survey = surveys.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    setting_updates: dict[str, Any] = {}
    if request.start_at is not None:
        setting_updates["start_at"] = request.start_at
    if request.end_at is not None:
        setting_updates["end_at"] = request.end_at
    if setting_updates:
        merged = survey.settings.model_dump(mode="python")
        merged.update(setting_updates)
        survey.settings = SurveySettings.model_validate(merged)

    if request.is_archived is not None:
        survey.is_archived = request.is_archived

    survey.updated_at = datetime.now(UTC)
    _audit(
        request.actor_id,
        request.actor_role,
        "survey.state.update",
        survey_id,
        {
            "is_archived": survey.is_archived,
            "start_at": survey.settings.start_at.isoformat(),
            "end_at": survey.settings.end_at.isoformat(),
        },
    )
    payload = survey.model_dump(mode="json")
    payload["is_active"] = survey.is_active()
    return payload


@app.get("/surveys/{survey_id}/widget-snippet")
async def widget_snippet(survey_id: str) -> dict[str, str]:
    survey = surveys.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    snippet = (
        "<iframe "
        f"src='https://votenow.local/embed/{survey.public_token}' "
        "width='100%' height='640' frameborder='0' loading='lazy'></iframe>"
    )
    return {"survey_id": survey_id, "snippet": snippet}


@app.get("/surveys/{survey_id}/recommendation")
async def survey_recommendation(survey_id: str) -> dict[str, str]:
    survey = surveys.get(survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    return {
        "survey_id": survey_id,
        "recommendation": survey_length_recommendation(len(survey.questions)),
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: VoteRole = VoteRole.ADMIN) -> dict[str, Any]:
    _assert_permission(actor_role, "audit:read")
    return {"items": audit_log[-limit:]}
