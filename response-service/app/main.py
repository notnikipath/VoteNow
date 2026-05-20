from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

from shared.votenow_common import (
    QuestionType,
    ResponseRecord,
    ResponseSaveRequest,
    ResponseSubmitRequest,
    Settings,
    Survey,
    check_captcha,
    duplicate_fingerprint,
    is_ip_rate_limited,
    register_ip_submission,
)

settings = Settings(service_name="response-service", service_port=8502)
app = FastAPI(title="VoteNow Response Service", version="1.0.0")

responses_by_survey: dict[str, list[ResponseRecord]] = {}
ip_submission_log: dict[str, list[datetime]] = {}


def _assert_survey_active(survey: Survey) -> None:
    if not survey.is_active():
        raise HTTPException(status_code=409, detail="Survey is closed")


def _validate_answers(survey: Survey, answers: list[dict[str, Any]]) -> None:
    questions = {question.question_id: question for question in survey.questions}
    answers_by_id = {item["question_id"]: item["value"] for item in answers}

    for question in survey.questions:
        if question.required and question.question_id not in answers_by_id:
            raise HTTPException(status_code=400, detail=f"Required question is missing: {question.question_id}")

    for question_id, value in answers_by_id.items():
        question = questions.get(question_id)
        if question is None:
            raise HTTPException(status_code=400, detail=f"Unknown question: {question_id}")
        if question.question_type == QuestionType.SINGLE:
            if not isinstance(value, str) or value not in question.options:
                raise HTTPException(status_code=400, detail=f"Invalid single-choice answer for {question_id}")
        elif question.question_type == QuestionType.MULTIPLE:
            if not isinstance(value, list) or not value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Multiple-choice answer must be a non-empty list: {question_id}",
                )
            if question.max_choices is not None and len(value) > question.max_choices:
                raise HTTPException(status_code=400, detail=f"Too many selected options for {question_id}")
            if any(option not in question.options for option in value):
                raise HTTPException(status_code=400, detail=f"Invalid option in answer for {question_id}")
        elif question.question_type == QuestionType.RATING:
            if not isinstance(value, int):
                raise HTTPException(status_code=400, detail=f"Rating answer must be integer: {question_id}")
            if value < question.rating_min or value > question.rating_max:
                raise HTTPException(status_code=400, detail=f"Rating is out of range for {question_id}")
            if (value - question.rating_min) % question.rating_step != 0:
                raise HTTPException(status_code=400, detail=f"Rating step mismatch for {question_id}")
        elif question.question_type == QuestionType.OPEN:
            if not isinstance(value, str):
                raise HTTPException(status_code=400, detail=f"Open answer must be string: {question_id}")
        elif question.question_type == QuestionType.TOURNAMENT:
            winners: list[str] = []
            if isinstance(value, dict):
                winners = [str(item) for item in value.values()]
            elif isinstance(value, list):
                winners = [str(item) for item in value]
            elif isinstance(value, str):
                winners = [value]
            else:
                raise HTTPException(status_code=400, detail=f"Invalid tournament answer for {question_id}")
            if any(item not in question.options for item in winners):
                raise HTTPException(status_code=400, detail=f"Unknown tournament winner for {question_id}")


async def _post_json(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _get_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/responses/save")
async def save_response(request: ResponseSaveRequest) -> dict[str, Any]:
    _assert_survey_active(request.survey)
    _validate_answers(request.survey, [item.model_dump(mode="python") for item in request.answers])

    response = ResponseRecord(
        response_id=f"RESP-{uuid4().hex[:10].upper()}",
        survey_id=request.survey.survey_id,
        respondent_id=request.respondent.respondent_id,
        ip_address=request.respondent.ip_address,
        answers=request.answers,
    )
    responses_by_survey.setdefault(request.survey.survey_id, []).append(response)
    register_ip_submission(ip_submission_log, request.survey.survey_id, request.respondent.ip_address)
    return response.model_dump(mode="json")


@app.post("/responses/submit")
async def submit_response(request: ResponseSubmitRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        survey_payload = await _get_json(client, f"{settings.survey_service_url}/surveys/{request.survey_id}")

    survey = Survey.model_validate(survey_payload)
    _assert_survey_active(survey)

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

    async with httpx.AsyncClient(timeout=15.0) as client:
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

    saved = await save_response(
        ResponseSaveRequest(
            survey=survey,
            answers=request.answers,
            respondent=request.respondent,
        )
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
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
                "response": saved,
            },
        )

    return saved


@app.get("/responses/{survey_id}")
async def list_responses(survey_id: str) -> dict[str, Any]:
    items = [item.model_dump(mode="json") for item in responses_by_survey.get(survey_id, [])]
    return {"items": items, "count": len(items)}


@app.get("/responses/{survey_id}/count")
async def response_count(survey_id: str) -> dict[str, int]:
    return {"survey_id": survey_id, "count": len(responses_by_survey.get(survey_id, []))}
