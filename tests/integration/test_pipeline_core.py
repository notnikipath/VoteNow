from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.helpers import load_module

ROOT = Path(__file__).resolve().parents[2]

survey_module = load_module("survey_module", ROOT / "survey-service" / "app" / "main.py")
response_module = load_module("response_module", ROOT / "response-service" / "app" / "main.py")
verification_module = load_module("verification_module", ROOT / "verification-service" / "app" / "main.py")
analytics_module = load_module("analytics_module", ROOT / "analytics-service" / "app" / "main.py")

survey_client = TestClient(survey_module.app)
response_client = TestClient(response_module.app)
verification_client = TestClient(verification_module.app)
analytics_client = TestClient(analytics_module.app)


def test_submit_pipeline_core() -> None:
    survey_response = survey_client.get("/surveys/SURVEY-DEMO")
    assert survey_response.status_code == 200
    survey = survey_response.json()

    duplicate_key = "SURVEY-DEMO:student-001"
    duplicate_check = verification_client.post("/verification/check-duplicate", json={"duplicate_key": duplicate_key})
    assert duplicate_check.status_code == 200

    saved = response_client.post(
        "/responses/save",
        json={
            "survey": survey,
            "answers": [
                {"question_id": "q1", "value": "Education"},
                {"question_id": "q2", "value": ["Real-time dashboard", "Export"]},
                {"question_id": "q3", "value": 8},
                {"question_id": "q4", "value": "Great and clear"},
                {"question_id": "q5", "value": "Workshop"},
            ],
            "respondent": {
                "respondent_id": "student-001",
                "email": "student001@example.com",
                "ip_address": "127.0.0.1",
                "user_agent": "pytest",
            },
        },
    )
    assert saved.status_code == 200

    analytics = analytics_client.post(
        "/analytics/live/update",
        json={
            "survey": survey,
            "response": saved.json(),
        },
    )
    assert analytics.status_code == 200

    duplicate_register = verification_client.post(
        "/verification/register-duplicate",
        json={"duplicate_key": duplicate_key},
    )
    assert duplicate_register.status_code == 200

    duplicate_check_again = verification_client.post(
        "/verification/check-duplicate",
        json={"duplicate_key": duplicate_key},
    )
    assert duplicate_check_again.status_code == 409


def test_verification_code_flow() -> None:
    code_request = verification_client.post(
        "/verification/request-code",
        json={
            "survey_id": "SURVEY-DEMO",
            "email": "student001@example.com",
            "method": "email",
            "actor_id": "admin",
            "actor_role": "admin",
        },
    )
    assert code_request.status_code == 200

    payload = code_request.json()
    code_confirm = verification_client.post(
        "/verification/confirm-code",
        json={"verification_id": payload["verification_id"], "code": payload["code_preview"]},
    )
    assert code_confirm.status_code == 200
