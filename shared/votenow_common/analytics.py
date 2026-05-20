from __future__ import annotations

from statistics import mean

from .schemas import QuestionType

POSITIVE_WORDS = {"good", "great", "excellent", "love", "fast", "clear", "easy"}
NEGATIVE_WORDS = {"bad", "poor", "hate", "slow", "hard", "confusing", "bug"}


def build_choice_distribution(values: list[str]) -> dict[str, int]:
    bucket: dict[str, int] = {}
    for value in values:
        key = str(value)
        bucket[key] = bucket.get(key, 0) + 1
    return bucket


def average_rating(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 2)


def sentiment_label(text: str) -> str:
    words = {part.strip(".,!?;:\"'").lower() for part in text.split() if part.strip()}
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def tournament_leader(wins: dict[str, int]) -> str | None:
    if not wins:
        return None
    return max(wins.items(), key=lambda item: item[1])[0]


def survey_length_recommendation(question_count: int) -> str:
    if question_count <= 8:
        return "Length is optimal for completion rate"
    if question_count <= 15:
        return "Moderate length, consider splitting optional questions"
    return "Survey is long, expected higher drop-off"


def forecast_turnout(current_count: int, elapsed_minutes: int, total_duration_minutes: int) -> int:
    if elapsed_minutes <= 0 or total_duration_minutes <= 0:
        return current_count
    per_minute = current_count / elapsed_minutes
    projected = int(per_minute * total_duration_minutes)
    return max(current_count, projected)


def response_throughput_ok(responses_last_minute: int, target_per_minute: int = 10000) -> bool:
    return responses_last_minute <= target_per_minute


def parallel_write_plan(target_responses_per_minute: int, shard_count: int) -> dict[str, int]:
    writers = max(2, min(64, shard_count * 2, target_responses_per_minute // 300))
    batch_size = max(50, target_responses_per_minute // max(writers, 1))
    return {"writers": writers, "batch_size": batch_size, "target_rpm": target_responses_per_minute}


def normalize_answer_for_type(question_type: QuestionType, value: object) -> list[str]:
    if question_type == QuestionType.MULTIPLE and isinstance(value, list):
        return [str(item) for item in value]
    if question_type == QuestionType.TOURNAMENT and isinstance(value, dict):
        return [str(item) for item in value.values()]
    return [str(value)]
