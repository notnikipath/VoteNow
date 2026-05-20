from __future__ import annotations

import json
import urllib.request

BASE = "http://localhost:8580"


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    response = request(
        "POST",
        "/workflow/submit-response",
        {
            "survey_id": "SURVEY-DEMO",
            "answers": [
                {"question_id": "q1", "value": "Education"},
                {"question_id": "q2", "value": ["Real-time dashboard", "Export"]},
                {"question_id": "q3", "value": 8},
                {"question_id": "q4", "value": "Great speed and very clear flow"},
                {"question_id": "q5", "value": "Workshop"},
            ],
            "respondent": {
                "respondent_id": "student-001",
                "email": "student001@example.com",
                "ip_address": "127.0.0.1",
                "user_agent": "demo-script",
            },
            "captcha_token": "ok",
            "verification_code": None,
        },
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
