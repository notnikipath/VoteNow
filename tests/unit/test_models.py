from datetime import UTC, datetime, timedelta

import pytest

from shared.votenow_common import QuestionType, SurveyQuestion, SurveySettings


def test_tournament_question_requires_even_options() -> None:
    with pytest.raises(ValueError):
        SurveyQuestion(
            question_id="q1",
            title="Choose",
            question_type=QuestionType.TOURNAMENT,
            options=["A", "B", "C"],
        )


def test_survey_dates_validation() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        SurveySettings(start_at=now, end_at=now - timedelta(minutes=5))
