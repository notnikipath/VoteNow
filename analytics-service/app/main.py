from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.votenow_common import (
    QuestionType,
    Settings,
    Survey,
    TTLCache,
    average_rating,
    build_choice_distribution,
    forecast_turnout,
    parallel_write_plan,
    response_throughput_ok,
    sentiment_label,
    survey_length_recommendation,
    tournament_leader,
)

settings = Settings(service_name="analytics-service", service_port=8504)
app = FastAPI(title="VoteNow Analytics Service", version="1.0.0")

analytics_store: dict[str, dict[str, Any]] = {}
responses_timeline: dict[str, list[datetime]] = {}
dashboard_cache = TTLCache(ttl_seconds=8)


class LiveUpdateRequest(BaseModel):
    survey: Survey
    response: dict[str, Any]


class EnsureStateRequest(BaseModel):
    survey: Survey


LiveUpdateRequest.model_rebuild()
EnsureStateRequest.model_rebuild()


def _ensure_state(survey: Survey) -> dict[str, Any]:
    existing = analytics_store.get(survey.survey_id)
    if existing is not None:
        return existing

    question_stats: dict[str, dict[str, Any]] = {}
    for question in survey.questions:
        if question.question_type in {QuestionType.SINGLE, QuestionType.MULTIPLE}:
            question_stats[question.question_id] = {
                "question_id": question.question_id,
                "title": question.title,
                "type": question.question_type.value,
                "counts": {option: 0 for option in question.options},
            }
        elif question.question_type == QuestionType.RATING:
            question_stats[question.question_id] = {
                "question_id": question.question_id,
                "title": question.title,
                "type": question.question_type.value,
                "values": [],
                "avg": 0.0,
            }
        elif question.question_type == QuestionType.OPEN:
            question_stats[question.question_id] = {
                "question_id": question.question_id,
                "title": question.title,
                "type": question.question_type.value,
                "sentiments": {"positive": 0, "negative": 0, "neutral": 0},
                "examples": [],
            }
        else:
            question_stats[question.question_id] = {
                "question_id": question.question_id,
                "title": question.title,
                "type": question.question_type.value,
                "wins": {option: 0 for option in question.options},
                "leader": None,
            }

    state = {
        "survey_id": survey.survey_id,
        "survey_title": survey.title,
        "question_count": len(survey.questions),
        "total_responses": 0,
        "question_stats": question_stats,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    analytics_store[survey.survey_id] = state
    return state


def _append_timeline(survey_id: str, submitted_at: str | None = None) -> None:
    now = datetime.now(UTC)
    if submitted_at:
        try:
            now = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
        except ValueError:
            now = datetime.now(UTC)
    responses_timeline.setdefault(survey_id, []).append(now)


def _responses_last_minute(survey_id: str) -> int:
    now = datetime.now(UTC)
    one_minute_ago = now - timedelta(minutes=1)
    filtered = [stamp for stamp in responses_timeline.get(survey_id, []) if stamp >= one_minute_ago]
    responses_timeline[survey_id] = filtered
    return len(filtered)


def _merge_answer(question_stat: dict[str, Any], value: Any) -> None:
    qtype = question_stat["type"]

    if qtype in {QuestionType.SINGLE.value, QuestionType.MULTIPLE.value}:
        values: list[str]
        if qtype == QuestionType.MULTIPLE.value and isinstance(value, list):
            values = [str(item) for item in value]
        else:
            values = [str(value)]

        distribution = build_choice_distribution(values)
        for option, count in distribution.items():
            question_stat["counts"][option] = question_stat["counts"].get(option, 0) + count
        return

    if qtype == QuestionType.RATING.value:
        try:
            question_stat["values"].append(float(value))
        except (TypeError, ValueError):
            return
        question_stat["avg"] = average_rating(question_stat["values"])
        return

    if qtype == QuestionType.OPEN.value:
        text = str(value)
        sentiment = sentiment_label(text)
        question_stat["sentiments"][sentiment] += 1
        if text.strip():
            question_stat["examples"].append(text.strip()[:160])
            question_stat["examples"] = question_stat["examples"][-8:]
        return

    winners: list[str] = []
    if isinstance(value, dict):
        winners = [str(item) for item in value.values()]
    elif isinstance(value, list):
        winners = [str(item) for item in value]
    else:
        winners = [str(value)]

    for winner in winners:
        question_stat["wins"][winner] = question_stat["wins"].get(winner, 0) + 1
    question_stat["leader"] = tournament_leader(question_stat["wins"])


def _dashboard_payload(survey_id: str) -> dict[str, Any]:
    cached = dashboard_cache.get(survey_id)
    if isinstance(cached, dict):
        return cached

    state = analytics_store.get(survey_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Survey analytics not found")

    responses_last_minute = _responses_last_minute(survey_id)
    elapsed_minutes = max(1, int((datetime.now(UTC) - state["created_at"]).total_seconds() // 60) + 1)
    survey_duration_minutes = max(60, elapsed_minutes * 3)

    payload = {
        "survey_id": survey_id,
        "survey_title": state["survey_title"],
        "total_responses": state["total_responses"],
        "responses_last_minute": responses_last_minute,
        "throughput_target_per_minute": settings.throughput_target_per_minute,
        "throughput_ok": response_throughput_ok(responses_last_minute, settings.throughput_target_per_minute),
        "projected_responses": forecast_turnout(
            current_count=state["total_responses"],
            elapsed_minutes=elapsed_minutes,
            total_duration_minutes=survey_duration_minutes,
        ),
        "question_count": state["question_count"],
        "length_recommendation": survey_length_recommendation(state["question_count"]),
        "page_load_target_seconds": settings.page_load_target_seconds,
        "estimated_widget_load_seconds": round(0.65 + state["question_count"] * 0.09, 2),
        "respondent_target": settings.respondent_target,
        "updated_at": state["updated_at"],
        "question_stats": state["question_stats"],
    }
    dashboard_cache.set(survey_id, payload)
    return payload


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/analytics/live/update")
async def update_live(request: LiveUpdateRequest) -> dict[str, Any]:
    state = _ensure_state(request.survey)

    answers = request.response.get("answers", [])
    for answer in answers:
        question_id = answer.get("question_id")
        question_stat = state["question_stats"].get(question_id)
        if question_stat is None:
            continue
        _merge_answer(question_stat, answer.get("value"))

    state["total_responses"] += 1
    state["updated_at"] = datetime.now(UTC)
    _append_timeline(request.survey.survey_id, request.response.get("submitted_at"))
    dashboard_cache.set(request.survey.survey_id, _dashboard_payload(request.survey.survey_id))
    return {
        "status": "updated",
        "survey_id": request.survey.survey_id,
        "total_responses": state["total_responses"],
    }


@app.post("/analytics/ensure-state")
async def ensure_state(request: EnsureStateRequest) -> dict[str, Any]:
    existed = request.survey.survey_id in analytics_store
    _ensure_state(request.survey)
    live = _dashboard_payload(request.survey.survey_id)
    return {
        "status": "ready",
        "created": not existed,
        "survey_id": request.survey.survey_id,
        "live": live,
    }


@app.get("/analytics/{survey_id}/live")
async def live_stats(survey_id: str) -> dict[str, Any]:
    return _dashboard_payload(survey_id)


@app.get("/analytics/{survey_id}/charts")
async def chart_data(survey_id: str) -> dict[str, Any]:
    dashboard = _dashboard_payload(survey_id)
    charts = []
    for stat in dashboard["question_stats"].values():
        if stat["type"] in {QuestionType.SINGLE.value, QuestionType.MULTIPLE.value}:
            charts.append({
                "question_id": stat["question_id"],
                "title": stat["title"],
                "kind": "bar",
                "labels": list(stat["counts"].keys()),
                "values": list(stat["counts"].values()),
            })
        elif stat["type"] == QuestionType.RATING.value:
            charts.append({
                "question_id": stat["question_id"],
                "title": stat["title"],
                "kind": "gauge",
                "avg": stat["avg"],
            })
        elif stat["type"] == QuestionType.OPEN.value:
            charts.append({
                "question_id": stat["question_id"],
                "title": stat["title"],
                "kind": "pie",
                "labels": ["positive", "neutral", "negative"],
                "values": [
                    stat["sentiments"]["positive"],
                    stat["sentiments"]["neutral"],
                    stat["sentiments"]["negative"],
                ],
            })
        else:
            charts.append({
                "question_id": stat["question_id"],
                "title": stat["title"],
                "kind": "tournament",
                "labels": list(stat["wins"].keys()),
                "values": list(stat["wins"].values()),
                "leader": stat["leader"],
            })
    return {"survey_id": survey_id, "charts": charts}


@app.get("/analytics/{survey_id}/tables")
async def table_data(survey_id: str) -> dict[str, Any]:
    dashboard = _dashboard_payload(survey_id)
    rows = []
    for stat in dashboard["question_stats"].values():
        rows.append(
            {
                "question_id": stat["question_id"],
                "title": stat["title"],
                "type": stat["type"],
                "payload": stat,
            }
        )
    return {"survey_id": survey_id, "rows": rows, "total_responses": dashboard["total_responses"]}


@app.get("/analytics/{survey_id}/forecast")
async def forecast(survey_id: str, total_duration_minutes: int = 180) -> dict[str, Any]:
    state = analytics_store.get(survey_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Survey analytics not found")
    elapsed = max(1, int((datetime.now(UTC) - state["created_at"]).total_seconds() // 60) + 1)
    projected = forecast_turnout(state["total_responses"], elapsed, total_duration_minutes)
    return {"survey_id": survey_id, "projected_responses": projected, "elapsed_minutes": elapsed}


@app.get("/analytics/{survey_id}/parallel-write-plan")
async def write_plan(survey_id: str, target_rpm: int = 10000, shards: int = 8) -> dict[str, Any]:
    if survey_id not in analytics_store:
        raise HTTPException(status_code=404, detail="Survey analytics not found")
    return parallel_write_plan(target_rpm, shards)
