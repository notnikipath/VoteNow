from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class QuestionType(str, Enum):
    SINGLE = "single_choice"
    MULTIPLE = "multiple_choice"
    RATING = "rating"
    OPEN = "open_text"
    TOURNAMENT = "tournament"


class SurveyVisibility(str, Enum):
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class VerificationMethod(str, Enum):
    NONE = "none"
    EMAIL = "email"
    SMS = "sms"


class VoteRole(str, Enum):
    RESPONDENT = "respondent"
    MODERATOR = "moderator"
    ANALYST = "analyst"
    ADMIN = "admin"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"


class ExportFormat(str, Enum):
    EXCEL = "excel"
    PDF = "pdf"


class SurveyQuestion(BaseModel):
    question_id: str
    title: str = Field(min_length=3, max_length=500)
    question_type: QuestionType
    required: bool = True
    description: str | None = None
    options: list[str] = Field(default_factory=list)
    rating_min: int = Field(default=1, ge=1, le=10)
    rating_max: int = Field(default=5, ge=2, le=10)
    rating_step: int = Field(default=1, ge=1, le=5)
    max_choices: int | None = Field(default=None, ge=1)
    next_map: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_by_type(self) -> SurveyQuestion:
        if self.question_type in {QuestionType.SINGLE, QuestionType.MULTIPLE, QuestionType.TOURNAMENT}:
            if len(self.options) < 2:
                raise ValueError("Choice and tournament questions require at least two options")
        if self.question_type == QuestionType.RATING and self.rating_min >= self.rating_max:
            raise ValueError("rating_min must be lower than rating_max")
        if self.question_type == QuestionType.MULTIPLE and self.max_choices is not None:
            if self.max_choices > len(self.options):
                raise ValueError("max_choices cannot exceed number of options")
        if self.question_type == QuestionType.TOURNAMENT and len(self.options) % 2 != 0:
            raise ValueError("Tournament questions require an even number of options")
        return self


class SurveySettings(BaseModel):
    visibility: SurveyVisibility = SurveyVisibility.PUBLIC
    start_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_at: datetime
    allow_anonymous: bool = True
    prevent_duplicates: bool = True
    invited_only: bool = False
    captcha_required: bool = True
    ip_limit_per_hour: int = Field(default=3, ge=1, le=100)
    verification_method: VerificationMethod = VerificationMethod.NONE
    show_live_dashboard: bool = True

    @model_validator(mode="after")
    def validate_dates(self) -> SurveySettings:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        return self


class SurveyCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str | None = None
    questions: list[SurveyQuestion] = Field(min_length=1)
    settings: SurveySettings
    created_by: str
    creator_role: VoteRole = VoteRole.MODERATOR


class Survey(BaseModel):
    survey_id: str
    public_token: str
    title: str
    description: str | None = None
    questions: list[SurveyQuestion]
    settings: SurveySettings
    created_by: str
    creator_role: VoteRole
    is_archived: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_active(self) -> bool:
        now = datetime.now(UTC)
        return (not self.is_archived) and self.settings.start_at <= now <= self.settings.end_at


class Respondent(BaseModel):
    respondent_id: str | None = None
    email: str | None = None
    phone: str | None = None
    ip_address: str
    user_agent: str | None = None


class AnswerPayload(BaseModel):
    question_id: str
    value: Any


class ResponseSubmitRequest(BaseModel):
    survey_id: str
    answers: list[AnswerPayload] = Field(min_length=1)
    respondent: Respondent
    captcha_token: str | None = None
    verification_code: str | None = None


class ResponseSaveRequest(BaseModel):
    survey: Survey
    answers: list[AnswerPayload] = Field(min_length=1)
    respondent: Respondent


class ResponseRecord(BaseModel):
    response_id: str
    survey_id: str
    respondent_id: str | None = None
    ip_address: str
    answers: list[AnswerPayload]
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InviteListRequest(BaseModel):
    survey_id: str
    allowed_ids: list[str] = Field(default_factory=list)


class NotificationPayload(BaseModel):
    channel: NotificationChannel
    recipient: str
    subject: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(BaseModel):
    event_id: str
    actor_id: str
    actor_role: VoteRole | str
    action: str
    object_type: str
    object_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
