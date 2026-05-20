from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

QUESTION_IDS = ["q1", "q2", "q3", "q4", "q5"]
SINGLE_OPTIONS = ["Education", "Community", "Corporate", "Events"]
MULTI_OPTIONS = ["Invited voting", "Real-time dashboard", "Export", "Integrations"]
TOURNAMENT_OPTIONS = ["Workshop", "Panel", "Networking", "Demo show"]
OPEN_RESPONSES = [
    "Great and clear experience",
    "Good overall but a bit slow",
    "Excellent for events",
    "Confusing in one section",
    "Love the live dashboard",
]


def sample_response(index: int) -> dict:
    return {
        "response_id": f"RESP-SAMPLE-{index:06d}",
        "survey_id": "SURVEY-DEMO",
        "respondent_id": f"sample-{index:06d}",
        "ip_address": f"10.0.{index % 255}.{(index * 7) % 255}",
        "submitted_at": (datetime.now(UTC) - timedelta(seconds=index * 3)).isoformat(),
        "answers": [
            {"question_id": QUESTION_IDS[0], "value": random.choice(SINGLE_OPTIONS)},
            {"question_id": QUESTION_IDS[1], "value": random.sample(MULTI_OPTIONS, k=2)},
            {"question_id": QUESTION_IDS[2], "value": random.randint(6, 10)},
            {"question_id": QUESTION_IDS[3], "value": random.choice(OPEN_RESPONSES)},
            {"question_id": QUESTION_IDS[4], "value": random.choice(TOURNAMENT_OPTIONS)},
        ],
    }


if __name__ == "__main__":
    random.seed(42)
    output = Path(__file__).resolve().parents[1] / "data" / "samples" / "votenow_responses.json"
    payload = [sample_response(index) for index in range(1, 6001)]
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload)} records to {output}")
