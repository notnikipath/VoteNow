from __future__ import annotations

from datetime import UTC, datetime, timedelta


def check_captcha(token: str | None, required: bool, shared_secret: str) -> bool:
    if not required:
        return True
    if token is None:
        return False
    allowed = {"ok", "passed", f"{shared_secret}:ok"}
    return token in allowed


def register_ip_submission(store: dict[str, list[datetime]], survey_id: str, ip_address: str) -> None:
    key = f"{survey_id}:{ip_address}"
    store.setdefault(key, []).append(datetime.now(UTC))


def is_ip_rate_limited(
    store: dict[str, list[datetime]],
    survey_id: str,
    ip_address: str,
    per_hour_limit: int,
) -> bool:
    key = f"{survey_id}:{ip_address}"
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)
    cleaned = [stamp for stamp in store.get(key, []) if stamp >= one_hour_ago]
    store[key] = cleaned
    return len(cleaned) >= per_hour_limit


def duplicate_fingerprint(
    survey_id: str,
    respondent_id: str | None,
    email: str | None,
    phone: str | None,
    ip_address: str,
) -> str:
    key = respondent_id or email or phone or ip_address
    return f"{survey_id}:{(key or ip_address).strip().lower()}"
